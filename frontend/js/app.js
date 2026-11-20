import {
  UnauthorizedError,
  getToken,
  listAnimals,
} from "./api.js";
import { askForToken } from "./auth.js";

const statusEl = document.querySelector("#status");
const listEl = document.querySelector("#animal-list");

function showStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function animalItem(animal) {
  const item = document.createElement("li");

  const number = document.createElement("a");
  number.className = "number";
  number.href = `animal.html?id=${encodeURIComponent(animal.id)}`;
  number.textContent = `#${animal.number}`;

  const details = document.createElement("div");
  details.className = "details";
  details.textContent = `${animal.sex} · ${animal.status} · born ${animal.date_of_birth ?? "unknown"}`;

  item.append(number, details);
  return item;
}

async function load() {
  listEl.replaceChildren();

  if (!getToken() && !askForToken()) {
    showStatus("A token is required to load animals.", true);
    return;
  }

  showStatus("Loading…");
  try {
    const animals = await listAnimals();
    listEl.replaceChildren(...animals.map(animalItem));
    showStatus(animals.length ? "" : "No animals yet.");
  } catch (error) {
    const message = error instanceof UnauthorizedError
      ? "Token rejected. Use “Set token” to try another."
      : `Could not load animals. ${error.message}`;
    showStatus(message, true);
  }
}

document.querySelector("#token-button").addEventListener("click", () => {
  if (askForToken()) load();
});

load();
