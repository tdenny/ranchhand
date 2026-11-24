import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

// A calf born at a calving: numbered after its dam, and its sex isn't known yet.
const calf = {
  id: "01CALF", number: "301's calf", sex: null, status: "active", date_of_birth: "2026-11-01",
  sire_id: null, dam_id: "01COW", castrated: false, breeding_state: null, due_date: null, category: "Calf",
};
const cow = { ...calf, id: "01COW", number: "301", sex: "female", dam_id: null, breeding_state: "open", category: "Cow" };

let calls = [];
let window;

before(async () => {
  const fetchStub = async (url, options = {}) => {
    const { pathname } = new URL(url);
    const method = options.method ?? "GET";
    calls.push({ method, pathname, body: options.body && JSON.parse(options.body) });

    if (method === "GET" && pathname === "/animals/01CALF") return jsonResponse(calf);
    if (method === "GET" && pathname === "/animals/01COW") return jsonResponse(cow);
    if (method === "GET" && pathname === "/animals") return jsonResponse({ animals: [cow, calf] });
    if (method === "PUT" && pathname === "/animals/01CALF") return jsonResponse({ ...calf, ...JSON.parse(options.body) });
    return jsonResponse({ message: "Not found" }, 404);
  };

  window = await loadPage("edit.html", { search: "?id=01CALF", fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const form = () => $("#animal-form");
const puts = () => calls.filter((c) => c.method === "PUT");

test("a calf of unknown sex shows no sex and has no breeding summary", async () => {
  await waitFor(() => !form().hidden, "the form");

  const { elements } = form();
  assert.equal(elements.sex.value, "");
  assert.equal(elements.sex.required, false);
  assert.equal($("#breeding-summary").hidden, true);
});

test("it can be retagged while its sex is still unknown", async () => {
  form().elements.number.value = "212";
  calls = [];

  form().requestSubmit();
  await waitFor(() => $("#form-status").textContent === "Saved.", "the save");

  assert.equal(puts()[0].body.number, "212");
  assert.equal(puts()[0].body.sex, null);
  assert.equal(puts()[0].body.breeding_state, null);
});

test("choosing a sex later sends it, and a heifer calf stays unbred", async () => {
  form().elements.sex.value = "female";
  form().elements.sex.dispatchEvent(new window.Event("change", { bubbles: true }));
  calls = [];

  form().requestSubmit();
  await waitFor(() => puts().length === 1, "the save");

  assert.equal(puts()[0].body.sex, "female");
  assert.equal(puts()[0].body.breeding_state, "unbred");
});
