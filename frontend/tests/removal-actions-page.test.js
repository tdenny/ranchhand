import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

// The API state: a removal event sets the status it leads to, as the real transaction does.
const NEXT_STATUS = { sold: "sold", died: "deceased", processed: "processed" };
let animal = {
  id: "01COW", number: "101", sex: "female", status: "active", date_of_birth: "2020-04-01",
  castrated: false, breeding_state: "pregnant", due_date: "2027-02-01", category: "Cow",
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
    if (method === "POST" && pathname === "/animals/01COW/removal-events") {
      const event = JSON.parse(options.body);
      animal = { ...animal, status: NEXT_STATUS[event.type] };
      return jsonResponse({ id: "01E1", animal_id: "01COW", ...event }, 201);
    }
    return jsonResponse({ message: "Not found" }, 404);
  };
  window = await loadPage("animal.html", { search: "?id=01COW", fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const actionLabels = () => [...window.document.querySelectorAll("#actions button")].map((b) => b.textContent);
const statusRow = () =>
  [...window.document.querySelectorAll("#profile-details dt")].find((dt) => dt.textContent === "Status")
    .nextElementSibling.textContent;

test("an active animal can be sold, die or be processed", async () => {
  await waitFor(() => actionLabels().length, "the action buttons");

  for (const label of ["Record sale", "Record death", "Record processing"]) {
    assert.ok(actionLabels().includes(label), label);
  }
});

test("recording a death posts a died event, sets the status and takes every action away", async () => {
  [...window.document.querySelectorAll("#actions button")].find((b) => b.textContent === "Record death").click();
  $("#action-form").elements.date.value = "2026-11-20";
  $("#action-form").elements.notes.value = "  blackleg ";
  calls = [];
  $("#action-form").requestSubmit();
  await waitFor(() => /recorded/.test($("#action-status").textContent), "the save");

  const posts = calls.filter((c) => c.method === "POST");
  assert.equal(posts.length, 1);
  assert.equal(posts[0].pathname, "/animals/01COW/removal-events");
  assert.deepEqual(posts[0].body, { type: "died", date: "2026-11-20", notes: "blackleg" });
  assert.equal($("#action-status").textContent, "Death recorded.");
  assert.equal($("#event-list").children[0].textContent, "Died2026-11-20blackleg");
  assert.equal(statusRow(), "deceased");
  assert.deepEqual(actionLabels(), [], "a removed animal has nothing left to record");
});
