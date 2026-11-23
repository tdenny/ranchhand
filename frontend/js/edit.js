import {
  ALL_STATUSES,
  NotFoundError,
  UnauthorizedError,
  ValidationError,
  getAnimal,
  getToken,
  listAnimals,
  updateAnimal,
} from "./api.js";
import { askForToken } from "./auth.js";
import { setupParentPicker } from "./parent-picker.js";

const animalId = new URLSearchParams(window.location.search).get("id");

const formEl = document.querySelector("#animal-form");
const statusEl = document.querySelector("#status");
const formStatusEl = document.querySelector("#form-status");

function showStatus(el, message, isError = false) {
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function loadErrorMessage(error) {
  if (error instanceof UnauthorizedError) return "Token rejected. Use “Set token” to try another.";
  if (error instanceof NotFoundError) return "Animal not found.";
  return `Could not load the animal. ${error.message}`;
}

// Same parent pickers as the add page: any animal can be a parent, whatever its status, so every
// status is fetched, when a picker first opens, and shared by both. A failure isn't remembered.
let candidates = null;

function loadCandidates() {
  candidates ??= listAnimals({ statuses: ALL_STATUSES }).catch((error) => {
    candidates = null;
    throw error;
  });
  return candidates;
}

// The picker shows the select's current option, so give it the animal's current parent up front
// rather than waiting for the full list to load. If the parent can't be looked up, its id stands in.
async function addCurrentParent(select, parentId) {
  if (!parentId) return;
  let label = parentId;
  try {
    label = `#${(await getAnimal(parentId)).number}`;
  } catch {
    // keep the id
  }
  select.append(new Option(label, parentId, true, true));
}

// The animal as the API last returned it. Its breeding state and due date aren't editable (only
// breeding events change them), so the form shows them as text and sends them back as they were.
let current = null;

const BREEDING_LABELS = { unbred: "Not yet bred", bred: "Bred", pregnant: "Pregnant", open: "Open" };

function showBreedingSummary() {
  const summaryEl = document.querySelector("#breeding-summary");
  const isFemale = formEl.elements.sex.value === "female";
  const state = current.breeding_state ?? "unbred"; // a male has none
  const due = state === "pregnant" && current.due_date ? `, due ${current.due_date}` : "";
  summaryEl.textContent = `Breeding: ${BREEDING_LABELS[state]}${due}. Record breeding events on the animal's page to change this.`;
  summaryEl.hidden = !isFemale;
}

// Only males can be castrated, and only females have a breeding state; a hidden box is cleared so a
// stale tick is never saved.
function showFlagFields() {
  const isMale = formEl.elements.sex.value === "male";
  document.querySelector("#castrated-field").hidden = !isMale;
  if (!isMale) formEl.elements.castrated.checked = false;
  showBreedingSummary();
}

async function fillForm(animal) {
  const { elements } = formEl;
  elements.number.value = animal.number;
  elements.sex.value = animal.sex;

  // External animals are made on their own page, and the add form doesn't offer the status, so
  // only an animal that already is external gets it as an option (and may lack a date of birth).
  const isExternal = animal.status === "external";
  const externalOption = elements.status.querySelector("option[value=external]");
  externalOption.hidden = externalOption.disabled = !isExternal;
  elements.status.value = animal.status;
  elements.date_of_birth.required = !isExternal;
  elements.date_of_birth.value = animal.date_of_birth ?? "";

  elements.castrated.checked = animal.castrated;
  current = animal;
  showFlagFields();

  await Promise.all([
    addCurrentParent(elements.sire_id, animal.sire_id),
    addCurrentParent(elements.dam_id, animal.dam_id),
  ]);
  setupParentPicker(elements.sire_id, { sex: "male", loadCandidates });
  setupParentPicker(elements.dam_id, { sex: "female", loadCandidates });

  document.querySelector("#edit-title").textContent = `Edit #${animal.number}`;
  document.querySelector("#back-link").href = `animal.html?id=${encodeURIComponent(animal.id)}`;
  document.querySelector("#back-link").textContent = `← #${animal.number}`;
  formEl.hidden = false;
}

async function load() {
  formEl.hidden = true;

  if (!animalId) {
    showStatus(statusEl, "No animal selected.", true);
    return;
  }
  if (!getToken() && !askForToken()) {
    showStatus(statusEl, "A token is required to load this animal.", true);
    return;
  }

  showStatus(statusEl, "Loading…");
  try {
    const animal = await getAnimal(animalId);
    await fillForm(animal);
    showStatus(statusEl, "");
  } catch (error) {
    showStatus(statusEl, loadErrorMessage(error), true);
  }
}

formEl.elements.sex.addEventListener("change", showFlagFields);

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!getToken() && !askForToken()) {
    showStatus(formStatusEl, "A token is required to save changes.", true);
    return;
  }

  const submitButton = formEl.querySelector("button[type=submit]");
  submitButton.disabled = true;
  showStatus(formStatusEl, "Saving…");

  const { elements } = formEl;
  const isFemale = elements.sex.value === "female";
  try {
    // The whole animal is sent, so cleared fields (no parent, no date of birth) are cleared.
    const animal = await updateAnimal(animalId, {
      number: elements.number.value,
      sex: elements.sex.value,
      status: elements.status.value,
      date_of_birth: elements.date_of_birth.value || null,
      sire_id: elements.sire_id.value,
      dam_id: elements.dam_id.value,
      castrated: elements.castrated.checked,
      breeding_state: isFemale ? (current.breeding_state ?? "unbred") : null,
      due_date: isFemale ? (current.due_date ?? null) : null,
    });
    current = animal;
    candidates = null; // the number may have changed, and so may who can be a parent
    document.querySelector("#edit-title").textContent = `Edit #${animal.number}`;
    document.querySelector("#back-link").textContent = `← #${animal.number}`;
    showStatus(formStatusEl, "Saved.");
  } catch (error) {
    let message = `Could not save the changes. ${error.message}`;
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

load();
