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

function renderProfile(animal) {
  titleEl.textContent = `#${animal.number}`;
  detailsEl.replaceChildren();
  // Unknown (null) when there is no date of birth, which is also when the sex stands in on the list.
  if (animal.category) addDetail("Category", animal.category);
  addDetail("Sex", animal.sex);
  addDetail("Status", animal.status);
  addDetail("Date of birth", animal.date_of_birth ?? "Unknown");
  profileEl.hidden = false;

  // Only the parents that are recorded get a row. Not awaited: they fill in as they arrive.
  if (animal.sire_id) addParent("Sire", animal.sire_id);
  if (animal.dam_id) addParent("Dam", animal.dam_id);
}

function eventItem(event) {
  const item = document.createElement("li");

  const heading = document.createElement("div");
  heading.className = "number";
  heading.textContent = event.type;

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

  const { type, date, notes } = Object.fromEntries(new FormData(formEl));

  try {
    const event = await createEvent(animalId, { type, date, notes: notes.trim() || null });
    // The list is newest first, so the new event goes on top.
    eventListEl.prepend(eventItem(event));
    showStatus(eventsStatusEl, "");
    resetForm();
    showStatus(formStatusEl, `Logged ${event.type}.`);
  } catch (error) {
    let message = `Could not log the event. ${error.message}`;
    if (error instanceof UnauthorizedError) {
      message = "Token rejected. Use “Set token” to try another.";
    } else if (error instanceof NotFoundError) {
      message = "Animal not found.";
    } else if (error instanceof ValidationError) {
      message = error.describe();
    }
    showStatus(formStatusEl, message, true);
  } finally {
    submitButton.disabled = false;
  }
});

document.querySelector("#token-button").addEventListener("click", () => {
  if (askForToken()) load();
});

resetForm();
load();
