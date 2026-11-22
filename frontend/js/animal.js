import {
  NotFoundError,
  UnauthorizedError,
  ValidationError,
  createEvent,
  getAnimal,
  getToken,
  listAnimalEvents,
} from "./api.js";
import { askForToken } from "./auth.js";

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
const milestoneActionsEl = document.querySelector("#milestone-actions");
const milestoneFormEl = document.querySelector("#milestone-form");
const milestoneTitleEl = document.querySelector("#milestone-title");
const milestoneStatusEl = document.querySelector("#milestone-status");

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

// The milestones that can be recorded from this page, and when each one applies to an animal.
const MILESTONE_ACTIONS = [
  {
    type: "castrated",
    label: "Record castration",
    done: "Castration recorded.",
    applies: (animal) => animal.sex === "male" && !animal.castrated,
  },
  // A cow is bred and calves again and again, so these stay available once recorded.
  {
    type: "bred",
    label: "Record breeding",
    done: "Breeding recorded.",
    applies: (animal) => animal.sex === "female",
  },
  {
    type: "calved",
    label: "Record calving",
    done: "Calving recorded.",
    applies: (animal) => animal.sex === "female",
  },
];

let activeAction = null;

function closeMilestoneForm() {
  activeAction = null;
  milestoneFormEl.hidden = true;
}

function openMilestoneForm(action) {
  activeAction = action;
  milestoneTitleEl.textContent = action.label;
  milestoneFormEl.reset();
  milestoneFormEl.elements.date.value = today();
  showStatus(milestoneStatusEl, "");
  milestoneFormEl.hidden = false;
  milestoneFormEl.elements.date.focus();
}

function renderMilestoneActions(animal) {
  closeMilestoneForm();
  const buttons = MILESTONE_ACTIONS.filter((action) => action.applies(animal)).map((action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "action";
    button.textContent = action.label;
    button.addEventListener("click", () => openMilestoneForm(action));
    return button;
  });
  milestoneActionsEl.replaceChildren(...buttons);
}

function renderProfile(animal) {
  titleEl.textContent = `#${animal.number}`;
  detailsEl.replaceChildren();
  // Unknown (null) when there is no date of birth, which is also when the sex stands in on the list.
  if (animal.category) addDetail("Category", animal.category);
  addDetail("Sex", animal.sex);
  addDetail("Status", animal.status);
  addDetail("Date of birth", animal.date_of_birth ?? "Unknown");
  document.querySelector("#edit-link").href = `edit.html?id=${encodeURIComponent(animal.id)}`;
  profileEl.hidden = false;
  renderMilestoneActions(animal);

  // Only the parents that are recorded get a row. Not awaited: they fill in as they arrive.
  if (animal.sire_id) addParent("Sire", animal.sire_id);
  if (animal.dam_id) addParent("Dam", animal.dam_id);
}

function eventItem(event) {
  const item = document.createElement("li");

  const heading = document.createElement("div");
  heading.className = "number";
  heading.textContent = event.type[0].toUpperCase() + event.type.slice(1);

  const details = document.createElement("div");
  details.className = "details";
  details.textContent = event.date;

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
    // This form only adds plain notes; milestones such as castration are recorded another way.
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

milestoneFormEl.addEventListener("submit", async (submitEvent) => {
  submitEvent.preventDefault();

  if (!getToken() && !askForToken()) {
    showStatus(milestoneStatusEl, "A token is required to record events.", true);
    return;
  }

  const action = activeAction;
  const submitButton = milestoneFormEl.querySelector("button[type=submit]");
  submitButton.disabled = true;
  showStatus(milestoneStatusEl, "Saving…");

  const { date, notes } = Object.fromEntries(new FormData(milestoneFormEl));

  try {
    const event = await createEvent(animalId, { type: action.type, date, notes: notes.trim() || null });
    eventListEl.prepend(eventItem(event));
    showStatus(eventsStatusEl, "");

    // The animal changed (its flag, and so its category), so show it again as the API now has it.
    try {
      renderProfile(await getAnimal(animalId));
      showStatus(milestoneStatusEl, action.done);
    } catch {
      closeMilestoneForm();
      showStatus(milestoneStatusEl, `${action.done} Reload the page to see the update.`);
    }
  } catch (error) {
    showStatus(milestoneStatusEl, saveErrorMessage(error), true);
  } finally {
    submitButton.disabled = false;
  }
});

document.querySelector("#milestone-cancel").addEventListener("click", () => {
  closeMilestoneForm();
  showStatus(milestoneStatusEl, "");
});

document.querySelector("#token-button").addEventListener("click", () => {
  if (askForToken()) load();
});

resetForm();
load();
