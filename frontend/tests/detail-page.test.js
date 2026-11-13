import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

const ANIMAL = { id: "01AAA", number: "101", sex: "female", status: "active", date_of_birth: "2022-04-01" };
const EVENTS = [
  { id: "01E2", animal_id: "01AAA", type: "weighing", date: "2024-06-01", notes: "540 lb" },
  { id: "01E1", animal_id: "01AAA", type: "vaccination", date: "2024-05-01", notes: null },
];

const calls = [];
let window;

// The page and its script load once per file, so the tests below share it and run in order.
before(async () => {
  const fetchStub = async (url, options = {}) => {
    const { pathname } = new URL(url);
    const method = options.method ?? "GET";
    calls.push({ method, pathname, body: options.body && JSON.parse(options.body) });

    if (method === "GET" && pathname === "/animals/01AAA") return jsonResponse(ANIMAL);
    if (method === "GET" && pathname === "/animals/01AAA/events") return jsonResponse({ events: EVENTS });
    if (method === "POST" && pathname === "/animals/01AAA/events") {
      return jsonResponse({ id: "01E3", animal_id: "01AAA", ...JSON.parse(options.body) }, 201);
    }
    return jsonResponse({ message: "Not found" }, 404);
  };

  window = await loadPage("animal.html", { search: "?id=01AAA", fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const eventItems = () => [...window.document.querySelectorAll("#event-list li")];

test("the detail page shows the animal and its events, newest first", async () => {
  await waitFor(() => eventItems().length === EVENTS.length, "events");

  assert.deepEqual(
    calls.map(({ method, pathname }) => `${method} ${pathname}`).sort(),
    ["GET /animals/01AAA", "GET /animals/01AAA/events"],
  );

  assert.equal($("#profile-title").textContent, "#101");
  const labels = [...window.document.querySelectorAll("#profile-details dt")].map((dt) => dt.textContent);
  const values = [...window.document.querySelectorAll("#profile-details dd")].map((dd) => dd.textContent);
  assert.deepEqual(
    Object.fromEntries(labels.map((label, i) => [label, values[i]])),
    { Sex: "female", Status: "active", "Date of birth": "2022-04-01" },
  );
  assert.deepEqual(
    eventItems().map((item) => item.textContent),
    ["weighing2024-06-01540 lb", "vaccination2024-05-01"],
  );
  assert.equal($("#status").textContent, "");
});

test("logging an event posts the trimmed form values and adds the event to the top of the list", async () => {
  const form = $("#event-form");
  assert.equal(form.elements.date.value, new Date().toLocaleDateString("en-CA"));

  form.elements.type.value = "treatment";
  form.elements.date.value = "2024-07-01";
  form.elements.notes.value = "  pinkeye  ";
  form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));

  await waitFor(() => $("#form-status").textContent === "Logged treatment.", "success message");

  const post = calls.find(({ method }) => method === "POST");
  assert.equal(post.pathname, "/animals/01AAA/events");
  assert.deepEqual(post.body, { type: "treatment", date: "2024-07-01", notes: "pinkeye" });

  assert.equal(eventItems().length, EVENTS.length + 1);
  assert.equal(eventItems()[0].textContent, "treatment2024-07-01pinkeye");
  assert.equal(form.elements.type.value, "", "the form is cleared after saving");
});
