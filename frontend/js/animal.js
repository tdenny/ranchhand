import {
  NotFoundError,
  UnauthorizedError,
  ValidationError,
  createBreedingEvent,
  createEvent,
  getAnimal,
  getToken,
  listAnimalEvents,
} from "./api.js";
import { askForToken } from "./auth.js";
import { BREEDING_LABELS, eventLabel } from "./labels.js";

const animalId = new URLSearchParams(window.location.search).get("id");

const statusEl = document.querySelector("#status");
const profileEl = document.querySelector("#profile");
const titleEl = document.querySelector("#profile-title");
const detailsEl = document.querySelector("#profile-details");
const eventsSectionEl = document.querySelector("#events-section");
const eventsStatusEl = document.querySelector("#events-status");
const eventListEl = document.querySelector("#event-list");
const formEl = document.querySelector("#event-form");
const formStatusEl = document.querySelector("#form-status");
const actionsEl = document.querySelector("#actions");
const actionFormEl = document.querySelector("#action-form");
const actionTitleEl = document.querySelector("#action-title");
const actionStatusEl = document.querySelector("#action-status");

function showStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function errorMessage(error, what) {
  if (error instanceof UnauthorizedError) return "Token rejected. Use “Set token” to try another.";
  if (error instanceof NotFoundError) return "Animal not found.";
  return `Could not load ${what}. ${error.message}`;
}

function addDetail(label, value) {
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  if (typeof value === "string") dd.textContent = value;
  else dd.append(value);
  detailsEl.append(dt, dd);
  return dd;
}

function parentLink(parent) {
  const link = document.createElement("a");
  link.href = `animal.html?id=${encodeURIComponent(parent.id)}`;
  link.textContent = `#${parent.number}`;
  return link;
}

// Show the sire or dam as a link by number. The profile only has the parent's id, so the number
// is looked up after the profile is on screen; until then (or if the lookup fails) the row says so.
async function addParent(label, parentId) {
  const dd = addDetail(label, "Loading…");
  try {
    dd.replaceChildren(parentLink(await getAnimal(parentId)));
  } catch (error) {
    dd.textContent = error instanceof NotFoundError ? "Not found" : "Could not load";
  }
}

// A female in one of these states; the same rules as TRANSITIONS in backend/src/ranchhand/models.py,
// which is what actually enforces them.
const femaleIn = (...states) => (animal) => animal.sex === "female" && states.includes(animal.breeding_state);
const BRED_OR_PREGNANT = femaleIn("bred", "pregnant");

// The events that can be recorded from this page, which endpoint takes each, and when it applies to an animal.
const ACTIONS = [
  {
    type: "castrated",
    create: createEvent,
    label: "Record castration",
    done: "Castration recorded.",
    applies: (animal) => animal.sex === "male" && !animal.castrated,
  },
  // A cow is bred again and again, whatever state she is in.
  {
    type: "bred",
    create: createBreedingEvent,
    label: "Record breeding",
    done: "Breeding recorded.",
    applies: (animal) => animal.sex === "female",
  },
  // A recheck of a pregnant cow is fine too, so she can be confirmed pregnant again (with a new due date).
  {
    type: "confirmed_pregnant",
    create: createBreedingEvent,
    label: "Confirm pregnant",
    done: "Pregnancy recorded.",
    dueDate: true,
    applies: BRED_OR_PREGNANT,
  },
  {
    type: "confirmed_open",
    create: createBreedingEvent,
    label: "Confirm open",
    done: "Open check recorded.",
    applies: BRED_OR_PREGNANT,
  },
  {
    type: "calved",
    create: createBreedingEvent,
    label: "Record calving",
    done: "Calving recorded.",
    // The API adds the calf to the herd, numbered after its dam until it gets an ear tag. Its sex
    // isn't asked for, since it often isn't known yet; it is set later by editing the calf.
    calf: true,
    applies: BRED_OR_PREGNANT,
  },
  {
    type: "lost",
    create: createBreedingEvent,
    label: "Record loss",
    done: "Loss recorded.",
    applies: femaleIn("pregnant"),
  },
];

let activeAction = null;

function closeActionForm() {
  activeAction = null;
  actionFormEl.hidden = true;
}

function openActionForm(action) {
  activeAction = action;
  actionTitleEl.textContent = action.label;
  actionFormEl.reset();
  actionFormEl.elements.date.value = today();
  document.querySelector("#action-due-field").hidden = !action.dueDate;
  showStatus(actionStatusEl, "");
  actionFormEl.hidden = false;
  actionFormEl.elements.date.focus();
}

function renderActions(animal) {
  closeActionForm();
  const buttons = ACTIONS.filter((action) => action.applies(animal)).map((action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "action";
    button.textContent = action.label;
    button.addEventListener("click", () => openActionForm(action));
    return button;
  });
  actionsEl.replaceChildren(...buttons);
}

function renderProfile(animal) {
  titleEl.textContent = `#${animal.number}`;
  detailsEl.replaceChildren();
  // Unknown (null) when there is no date of birth, which is also when the sex stands in on the list.
  if (animal.category) addDetail("Category", animal.category);
  addDetail("Sex", animal.sex ?? "Unknown");
  addDetail("Status", animal.status);
  addDetail("Date of birth", animal.date_of_birth ?? "Unknown");
  // Only females have a breeding state, and only a pregnant one may have a due date.
  if (animal.breeding_state) addDetail("Breeding", BREEDING_LABELS[animal.breeding_state]);
  if (animal.due_date) addDetail("Due", animal.due_date);
  document.querySelector("#edit-link").href = `edit.html?id=${encodeURIComponent(animal.id)}`;
  profileEl.hidden = false;
  renderActions(animal);

  // Only the parents that are recorded get a row. Not awaited: they fill in as they arrive.
  if (animal.sire_id) addParent("Sire", animal.sire_id);
  if (animal.dam_id) addParent("Dam", animal.dam_id);
}

function eventItem(event) {
  const item = document.createElement("li");

  const heading = document.createElement("div");
  heading.className = "number";
  heading.textContent = eventLabel(event.type);

  const details = document.createElement("div");
  details.className = "details";
  details.textContent = event.due_date ? `${event.date} · due ${event.due_date}` : event.date;

  item.append(heading, details);

  if (event.notes) {
    const notes = document.createElement("div");
    notes.textContent = event.notes;
    item.append(notes);
  }
  return item;
}

function renderEvents(events) {
  eventListEl.replaceChildren(...events.map(eventItem));
  showStatus(eventsStatusEl, events.length ? "" : "No events yet.");
  eventsSectionEl.hidden = false;
}

async function load() {
  profileEl.hidden = true;
  eventsSectionEl.hidden = true;

  if (!animalId) {
    showStatus(statusEl, "No animal selected.", true);
    return;
  }
  if (!getToken() && !askForToken()) {
    showStatus(statusEl, "A token is required to load this animal.", true);
    return;
  }

  showStatus(statusEl, "Loading…");
  const profileRequest = getAnimal(animalId);
  const eventsRequest = listAnimalEvents(animalId);

  // Handle the two results independently so a failure in one does not hide the other.
  const [profile, events] = await Promise.allSettled([profileRequest, eventsRequest]);

  if (profile.status === "rejected") {
    showStatus(statusEl, errorMessage(profile.reason, "the animal"), true);
    return;
  }
  showStatus(statusEl, "");
  renderProfile(profile.value);

  if (events.status === "rejected") {
    showStatus(eventsStatusEl, errorMessage(events.reason, "events"), true);
    eventsSectionEl.hidden = false;
    return;
  }
  renderEvents(events.value);
}

function saveErrorMessage(error) {
  if (error instanceof UnauthorizedError) return "Token rejected. Use “Set token” to try another.";
  if (error instanceof NotFoundError) return "Animal not found.";
  if (error instanceof ValidationError) return error.describe();
  return `Could not log the event. ${error.message}`;
}

// Today as YYYY-MM-DD in the user's timezone (toISOString would use UTC).
function today() {
  return new Date().toLocaleDateString("en-CA");
}

function resetForm() {
  formEl.reset();
  formEl.elements.date.value = today();
}

formEl.addEventListener("submit", async (submitEvent) => {
  submitEvent.preventDefault();

  if (!getToken() && !askForToken()) {
    showStatus(formStatusEl, "A token is required to log events.", true);
    return;
  }

  const submitButton = formEl.querySelector("button[type=submit]");
  submitButton.disabled = true;
  showStatus(formStatusEl, "Saving…");

  const { date, notes } = Object.fromEntries(new FormData(formEl));

  try {
    // This form only adds plain notes; castration and breeding events are recorded with the action buttons.
    const event = await createEvent(animalId, { type: "note", date, notes: notes.trim() || null });
    // The list is newest first, so the new event goes on top.
    eventListEl.prepend(eventItem(event));
    showStatus(eventsStatusEl, "");
    resetForm();
    showStatus(formStatusEl, "Note added.");
  } catch (error) {
    const message = saveErrorMessage(error);
    showStatus(formStatusEl, message, true);
  } finally {
    submitButton.disabled = false;
  }
});

actionFormEl.addEventListener("submit", async (submitEvent) => {
  submitEvent.preventDefault();

  if (!getToken() && !askForToken()) {
    showStatus(actionStatusEl, "A token is required to record events.", true);
    return;
  }

  const action = activeAction;
  const submitButton = actionFormEl.querySelector("button[type=submit]");
  submitButton.disabled = true;
  showStatus(actionStatusEl, "Saving…");

  const { date, notes, due_date: dueDate } = Object.fromEntries(new FormData(actionFormEl));

  try {
    // Only a confirmed pregnancy takes a due date; left out, the API works one out from the last breeding.
    const event = await action.create(animalId, {
      type: action.type,
      date,
      notes: notes.trim() || null,
      ...(action.dueDate && dueDate && { due_date: dueDate }),
      ...(action.calf && { calf: {} }),
    });
    eventListEl.prepend(eventItem(event));
    showStatus(eventsStatusEl, "");

    // The animal changed (its flag, and so its category), so show it again as the API now has it.
    try {
      renderProfile(await getAnimal(animalId));
      showStatus(actionStatusEl, action.done);
    } catch {
      closeActionForm();
      showStatus(actionStatusEl, `${action.done} Reload the page to see the update.`);
    }
  } catch (error) {
    showStatus(actionStatusEl, saveErrorMessage(error), true);
  } finally {
    submitButton.disabled = false;
  }
});

document.querySelector("#action-cancel").addEventListener("click", () => {
  closeActionForm();
  showStatus(actionStatusEl, "");
});

document.querySelector("#token-button").addEventListener("click", () => {
  if (askForToken()) load();
});

resetForm();
load();
