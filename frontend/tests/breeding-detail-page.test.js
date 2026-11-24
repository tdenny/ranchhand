import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

const COW = {
  id: "01COW", number: "101", sex: "female", status: "active", date_of_birth: "2020-04-01",
  castrated: false, breeding_state: "pregnant", due_date: "2027-02-01", category: "Cow",
};
const EVENTS = [
  { id: "01E4", animal_id: "01COW", type: "lost", date: "2026-09-01", notes: null, due_date: null },
  { id: "01E3", animal_id: "01COW", type: "confirmed_pregnant", date: "2026-05-01", notes: null, due_date: "2027-02-01" },
  { id: "01E2", animal_id: "01COW", type: "confirmed_open", date: "2025-12-01", notes: "vet check", due_date: null },
  { id: "01E1", animal_id: "01COW", type: "bred", date: "2025-09-01", notes: null, due_date: null },
];

let window;

async function fetchStub(url) {
  const { pathname } = new URL(url);
  if (pathname === "/animals/01COW") return jsonResponse(COW);
  if (pathname.endsWith("/events")) return jsonResponse({ events: EVENTS });
  return jsonResponse({ message: "Not found" }, 404);
}

before(async () => {
  window = await loadPage("animal.html", { search: "?id=01COW", fetchStub });
});

const details = () => {
  const labels = [...window.document.querySelectorAll("#profile-details dt")].map((dt) => dt.textContent);
  const values = [...window.document.querySelectorAll("#profile-details dd")].map((dd) => dd.textContent);
  return Object.fromEntries(labels.map((label, i) => [label, values[i]]));
};

test("a pregnant cow shows her breeding state and due date", async () => {
  await waitFor(() => window.document.querySelectorAll("#event-list li").length, "events");

  assert.equal(details().Breeding, "Pregnant");
  assert.equal(details().Due, "2027-02-01");
});

test("breeding events read as words, and a confirmed pregnancy shows its due date", () => {
  const items = [...window.document.querySelectorAll("#event-list li")].map((li) => li.textContent);

  assert.deepEqual(items, [
    "Lost pregnancy2026-09-01",
    "Confirmed pregnant2026-05-01 · due 2027-02-01",
    "Confirmed open2025-12-01vet check",
    "Bred2025-09-01",
  ]);
});
