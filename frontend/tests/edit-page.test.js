import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

const cow = {
  id: "01COW", number: "301", sex: "female", status: "active", date_of_birth: "2020-04-01",
  sire_id: "01BULL", dam_id: null, castrated: false, bred: true, category: "Cow",
};
const bull = { ...cow, id: "01BULL", number: "201", sex: "male", sire_id: null, bred: false, category: "Bull" };

let calls = [];
let rejectNextPut = false;
let window;

before(async () => {
  const fetchStub = async (url, options = {}) => {
    const { pathname } = new URL(url);
    const method = options.method ?? "GET";
    calls.push({ method, pathname, body: options.body && JSON.parse(options.body) });

    if (method === "GET" && pathname === "/animals/01COW") return jsonResponse(cow);
    if (method === "GET" && pathname === "/animals/01BULL") return jsonResponse(bull);
    if (method === "GET" && pathname === "/animals") return jsonResponse({ animals: [bull, cow] });
    if (method === "PUT" && pathname === "/animals/01COW") {
      if (rejectNextPut) {
        rejectNextPut = false;
        return jsonResponse({ errors: [{ loc: ["body", "number"], msg: "bad number" }] }, 400);
      }
      return jsonResponse({ ...cow, ...JSON.parse(options.body) });
    }
    return jsonResponse({ message: "Not found" }, 404);
  };

  window = await loadPage("edit.html", { search: "?id=01COW", fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const form = () => $("#animal-form");
const puts = () => calls.filter((c) => c.method === "PUT");

test("the form is filled with the animal's current values, including its parent", async () => {
  await waitFor(() => !form().hidden, "the form");

  const { elements } = form();
  assert.equal(elements.number.value, "301");
  assert.equal(elements.sex.value, "female");
  assert.equal(elements.status.value, "active");
  assert.equal(elements.date_of_birth.value, "2020-04-01");
  assert.equal(elements.sire_id.value, "01BULL");
  assert.equal(elements.dam_id.value, "");
  assert.equal(elements.bred.checked, true);
  assert.equal($("#bred-field").hidden, false);
  assert.equal($("#castrated-field").hidden, true);
  assert.equal($("#edit-title").textContent, "Edit #301");
});

test("saving PUTs the complete animal, so a cleared field is sent as cleared", async () => {
  const { elements } = form();
  elements.number.value = "302";
  elements.status.value = "sold";
  elements.sire_id.value = "";
  elements.bred.checked = false;
  calls = [];

  form().requestSubmit();
  await waitFor(() => $("#form-status").textContent === "Saved.", "the success message");

  assert.deepEqual(puts()[0].body, {
    number: "302", sex: "female", status: "sold", date_of_birth: "2020-04-01",
    sire_id: "", dam_id: "", castrated: false, bred: false,
  });
  assert.equal($("#edit-title").textContent, "Edit #302");
});

test("a validation error from the API is shown and nothing claims to be saved", async () => {
  rejectNextPut = true;

  form().requestSubmit();
  await waitFor(() => $("#form-status").classList.contains("error"), "the error");

  assert.equal($("#form-status").textContent, "number: bad number");
});
