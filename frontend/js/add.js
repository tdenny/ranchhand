import {
  ALL_STATUSES,
  UnauthorizedError,
  ValidationError,
  createAnimal,
  getToken,
  listAnimals,
} from "./api.js";
import { askForToken } from "./auth.js";
import { setupParentPicker } from "./parent-picker.js";

const formEl = document.querySelector("#animal-form");
const formStatusEl = document.querySelector("#form-status");

// Parents can be any animal, whatever its status (a deceased sire, an external bull), so the
// pickers fetch every status. Fetched when a picker first opens and shared by both; a failure
// isn't remembered, so the next open retries.
let candidates = null;

function loadCandidates() {
  candidates ??= listAnimals({ statuses: ALL_STATUSES }).catch((error) => {
    candidates = null;
    throw error;
  });
  return candidates;
}

setupParentPicker(document.querySelector("#sire"), { sex: "male", loadCandidates });
setupParentPicker(document.querySelector("#dam"), { sex: "female", loadCandidates });

// Only males can be castrated and only females bred, so show whichever applies to the chosen sex.
// A hidden box is cleared so a tick left over from the other sex is never submitted.
function showFlagFields() {
  const isMale = formEl.elements.sex.value === "male";
  for (const [id, applies] of [["castrated", isMale], ["bred", !isMale]]) {
    document.querySelector(`#${id}-field`).hidden = !applies;
    if (!applies) formEl.elements[id].checked = false;
  }
}

formEl.elements.sex.addEventListener("change", showFlagFields);
showFlagFields();

function showStatus(message, isError = false) {
  formStatusEl.textContent = message;
  formStatusEl.classList.toggle("error", isError);
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!getToken() && !askForToken()) {
    showStatus("A token is required to add animals.", true);
    return;
  }

  const submitButton = formEl.querySelector("button[type=submit]");
  submitButton.disabled = true;
  showStatus("Saving…");

  try {
    // An unchecked box is left out of the form data, and the API treats a missing flag as false.
    const { castrated, bred, ...fields } = Object.fromEntries(new FormData(formEl));
    const animal = await createAnimal({
      ...fields,
      ...(castrated && { castrated: true }),
      ...(bred && { bred: true }),
    });
    candidates = null; // the new animal can be a parent from now on
    formEl.reset();
    showFlagFields(); // reset puts the sex back to its default without firing a change event
    showStatus(`Added #${animal.number}.`, false);
  } catch (error) {
    let message = `Could not add the animal. ${error.message}`;
    if (error instanceof UnauthorizedError) {
      message = "Token rejected. Use “Set token” to try another.";
    } else if (error instanceof ValidationError) {
      message = error.describe();
    }
    showStatus(message, true);
  } finally {
    submitButton.disabled = false;
  }
});

document.querySelector("#token-button").addEventListener("click", () => askForToken());
