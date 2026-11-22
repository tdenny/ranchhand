import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

// The API state: recording breeding or calving sets the bred flag, as the real transaction does.
let animal = {
  id: "01COW", number: "101", sex: "female", status: "active", date_of_birth: "2020-04-01",
  castrated: false, bred: false, category: "Heifer",
};
let calls = [];
let window;

before(async () => {
  const fetchStub = async (url, options = {}) => {
    const { pathname } = new URL(url);
    const method = options.method ?? "GET";
    calls.push({ method, pathname, body: options.body && JSON.parse(options.body) });

    if (method === "GET" && pathname === "/animals/01COW") return jsonResponse(animal);
    if (method === "GET" && pathname === "/animals/01COW/events") return jsonResponse({ events: [] });
    if (method === "POST" && pathname === "/animals/01COW/events") {
      animal = { ...animal, bred: true, category: "Cow" };
      return jsonResponse({ id: "01E1", animal_id: "01COW", ...JSON.parse(options.body) }, 201);
    }
    return jsonResponse({ message: "Not found" }, 404);
  };

  window = await loadPage("animal.html", { search: "?id=01COW", fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const actionButtons = () => [...window.document.querySelectorAll("#milestone-actions button")];
const labels = () => actionButtons().map((b) => b.textContent);
const posts = () => calls.filter((c) => c.method === "POST");
const category = () => {
  const dts = [...window.document.querySelectorAll("#profile-details dt")];
  return dts.find((dt) => dt.textContent === "Category")?.nextElementSibling.textContent;
};

async function record(buttonLabel, date) {
  actionButtons().find((b) => b.textContent === buttonLabel).click();
  $("#milestone-form").elements.date.value = date;
  calls = [];
  $("#milestone-form").requestSubmit();
  await waitFor(() => posts().length === 1 && /recorded/.test($("#milestone-status").textContent), "the save");
}

test("a female gets breeding and calving buttons but no castration button", async () => {
  await waitFor(() => actionButtons().length, "the action buttons");

  assert.deepEqual(labels(), ["Record breeding", "Record calving"]);
  assert.equal($("#milestone-form").hidden, true);
  assert.equal(category(), "Heifer");
});

test("recording breeding posts a bred event and the heifer becomes a cow", async () => {
  await record("Record breeding", "2026-05-01");

  assert.deepEqual(posts()[0].body, { type: "bred", date: "2026-05-01", notes: null });
  assert.equal($("#milestone-status").textContent, "Breeding recorded.");
  assert.equal($("#event-list").children[0].textContent, "Bred2026-05-01");
  assert.equal(category(), "Cow");
});

test("breeding and calving stay available once the cow is bred, and calving posts a calved event", async () => {
  assert.deepEqual(labels(), ["Record breeding", "Record calving"]);

  await record("Record calving", "2026-11-10");

  assert.deepEqual(posts()[0].body, { type: "calved", date: "2026-11-10", notes: null });
  assert.equal($("#milestone-status").textContent, "Calving recorded.");
  assert.equal($("#event-list").children[0].textContent, "Calved2026-11-10");
});
