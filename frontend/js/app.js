import {
  UnauthorizedError,
  ValidationError,
  createAnimal,
  getToken,
  listAnimals,
} from "./api.js";
import { askForToken } from "./auth.js";

const statusEl = document.querySelector("#status");
const listEl = document.querySelector("#animal-list");
const formEl = document.querySelector("#animal-form");
const formStatusEl = document.querySelector("#form-status");

function showStatus(message, isError = false, el = statusEl) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function animalItem(animal) {
  const item = document.createElement("li");

  const number = document.createElement("a");
  number.className = "number";
  number.href = `animal.html?id=${encodeURIComponent(animal.id)}`;
  number.textContent = `#${animal.number}`;

  const details = document.createElement("div");
  details.className = "details";
  details.textContent = `${animal.sex} · ${animal.status} · born ${animal.date_of_birth}`;

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

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!getToken() && !askForToken()) {
    showStatus("A token is required to add animals.", true, formStatusEl);
    return;
  }

  const submitButton = formEl.querySelector("button[type=submit]");
  submitButton.disabled = true;
  showStatus("Saving…", false, formStatusEl);

  try {
    const animal = await createAnimal(Object.fromEntries(new FormData(formEl)));
    listEl.append(animalItem(animal));
    showStatus("", false);
    formEl.reset();
    showStatus(`Added #${animal.number}.`, false, formStatusEl);
  } catch (error) {
    let message = `Could not add the animal. ${error.message}`;
    if (error instanceof UnauthorizedError) {
      message = "Token rejected. Use “Set token” to try another.";
    } else if (error instanceof ValidationError) {
      message = error.describe();
    }
    showStatus(message, true, formStatusEl);
  } finally {
    submitButton.disabled = false;
  }
});

document.querySelector("#token-button").addEventListener("click", () => {
  if (askForToken()) load();
});

load();
