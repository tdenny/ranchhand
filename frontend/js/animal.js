import {
  NotFoundError,
  UnauthorizedError,
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

function showStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function errorMessage(error, what) {
  if (error instanceof UnauthorizedError) return "Token rejected. Use “Set token” to try another.";
  if (error instanceof NotFoundError) return "Animal not found.";
  return `Could not load ${what}. ${error.message}`;
}

function renderProfile(animal) {
  titleEl.textContent = `#${animal.number}`;
  const fields = [
    ["Sex", animal.sex],
    ["Status", animal.status],
    ["Date of birth", animal.date_of_birth],
  ];
  detailsEl.replaceChildren(...fields.flatMap(([label, value]) => {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    return [dt, dd];
  }));
  profileEl.hidden = false;
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

document.querySelector("#token-button").addEventListener("click", () => {
  if (askForToken()) load();
});

load();
