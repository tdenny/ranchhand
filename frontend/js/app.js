import {
  UnauthorizedError,
  getToken,
  listAnimals,
} from "./api.js";
import { askForToken } from "./auth.js";

const statusEl = document.querySelector("#status");
const listEl = document.querySelector("#animal-list");
const filtersEl = document.querySelector("#filters");

// The quick filters shown above the list. To add one, add an entry here: `matches` gets an animal as the API returns it.
const FILTERS = [
  { label: "All", matches: () => true },
  { label: "Calves", matches: (animal) => animal.category?.endsWith("calf") ?? false },
  { label: "Open cows", matches: (animal) => animal.category === "Cow" && animal.breeding_state === "open" },
  { label: "Pregnant cows", matches: (animal) => animal.category === "Cow" && animal.breeding_state === "pregnant" },
  { label: "Steers", matches: (animal) => animal.category === "Steer" },
];

let animals = [];
let activeFilter = FILTERS[0];

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
  details.textContent = `${animal.category ?? animal.sex ?? "sex unknown"} · ${animal.status} · born ${animal.date_of_birth ?? "unknown"}`;

  item.append(number, details);
  return item;
}

function renderList() {
  const shown = animals.filter(activeFilter.matches);
  listEl.replaceChildren(...shown.map(animalItem));
  if (!animals.length) showStatus("No animals yet.");
  else showStatus(shown.length ? "" : `No animals match “${activeFilter.label}”.`);
  for (const button of filtersEl.children) {
    button.setAttribute("aria-pressed", String(button.textContent === activeFilter.label));
  }
}

function renderFilters() {
  filtersEl.replaceChildren(...FILTERS.map((filter) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "filter";
    button.textContent = filter.label;
    button.addEventListener("click", () => {
      activeFilter = filter;
      renderList();
    });
    return button;
  }));
}

async function load() {
  listEl.replaceChildren();

  if (!getToken() && !askForToken()) {
    showStatus("A token is required to load animals.", true);
    return;
  }

  showStatus("Loading…");
  try {
    animals = await listAnimals();
    renderList();
  } catch (error) {
    const message = error instanceof UnauthorizedError
      ? "Token rejected. Use “Set token” to try another."
      : `Could not load animals. ${error.message}`;
    showStatus(message, true);
  }
}

document.querySelector("#token-button").addEventListener("click", () => {
  if (askForToken()) renderFilters();
load();
});

renderFilters();
load();
