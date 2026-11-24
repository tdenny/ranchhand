import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

// The API state: each breeding event moves the animal to the state it leads to, as the real transaction does.
const NEXT_STATE = { bred: "bred", confirmed_pregnant: "pregnant", confirmed_open: "open", calved: "open", lost: "open" };
let animal = {
  id: "01COW", number: "101", sex: "female", status: "active", date_of_birth: "2020-04-01",
  castrated: false, breeding_state: "unbred", due_date: null, category: "Heifer",
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
    if (method === "POST" && pathname === "/animals/01COW/breeding-events") {
      const event = JSON.parse(options.body);
      animal = { ...animal, breeding_state: NEXT_STATE[event.type], due_date: event.due_date ?? null, category: "Cow" };
      return jsonResponse({ id: "01E1", animal_id: "01COW", ...event }, 201);
    }
    return jsonResponse({ message: "Not found" }, 404);
  };

  window = await loadPage("animal.html", { search: "?id=01COW", fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const actionButtons = () => [...window.document.querySelectorAll("#actions button")];
const labels = () => actionButtons().map((b) => b.textContent);
const posts = () => calls.filter((c) => c.method === "POST");
const category = () => {
  const dts = [...window.document.querySelectorAll("#profile-details dt")];
  return dts.find((dt) => dt.textContent === "Category")?.nextElementSibling.textContent;
};

const detailRows = () => {
  const labels = [...window.document.querySelectorAll("#profile-details dt")].map((dt) => dt.textContent);
  const values = [...window.document.querySelectorAll("#profile-details dd")].map((dd) => dd.textContent);
  const rows = Object.fromEntries(labels.map((label, i) => [label, values[i]]));
  return { ...(rows.Breeding && { Breeding: rows.Breeding }), ...(rows.Due && { Due: rows.Due }) };
};

async function record(buttonLabel, date) {
  actionButtons().find((b) => b.textContent === buttonLabel).click();
  $("#action-form").elements.date.value = date;
  calls = [];
  $("#action-form").requestSubmit();
  await waitFor(() => posts().length === 1 && /recorded/.test($("#action-status").textContent), "the save");
}

const BRED_BUTTONS = ["Record breeding", "Confirm pregnant", "Confirm open", "Record calving"];
const PREGNANT_BUTTONS = [...BRED_BUTTONS, "Record loss"];

// The tests below run in order and share the page, so each one starts in the state the last one left.

test("a cow that has never been bred can only be bred, not checked, calved or lost", async () => {
  await waitFor(() => actionButtons().length, "the action buttons");

  assert.deepEqual(labels(), ["Record breeding"]);
  assert.equal($("#action-form").hidden, true);
  assert.equal(category(), "Heifer");
});

test("recording breeding posts a bred event, the heifer becomes a cow and the checks open up", async () => {
  await record("Record breeding", "2026-05-01");

  assert.deepEqual(posts()[0].body, { type: "bred", date: "2026-05-01", notes: null });
  assert.equal(posts()[0].pathname, "/animals/01COW/breeding-events");
  assert.equal($("#action-status").textContent, "Breeding recorded.");
  assert.equal($("#event-list").children[0].textContent, "Bred2026-05-01");
  assert.equal(category(), "Cow");
  assert.deepEqual(labels(), BRED_BUTTONS, "a bred cow can be checked or calve, but not lose a pregnancy");
});

test("confirming a pregnancy posts the due date, and the profile shows the new state", async () => {
  actionButtons().find((b) => b.textContent === "Confirm pregnant").click();
  assert.equal($("#action-due-field").hidden, false);
  $("#action-form").elements.date.value = "2026-05-20";
  $("#action-form").elements.due_date.value = "2027-02-01";
  calls = [];
  $("#action-form").requestSubmit();
  await waitFor(() => posts().length === 1 && /recorded/.test($("#action-status").textContent), "the save");

  assert.deepEqual(posts()[0].body, { type: "confirmed_pregnant", date: "2026-05-20", notes: null, due_date: "2027-02-01" });
  assert.equal($("#action-status").textContent, "Pregnancy recorded.");
  assert.equal($("#event-list").children[0].textContent, "Confirmed pregnant2026-05-20 · due 2027-02-01");
  assert.deepEqual(detailRows(), { Breeding: "Pregnant", Due: "2027-02-01" });
  assert.deepEqual(labels(), PREGNANT_BUTTONS, "only a pregnant cow can lose a pregnancy");
});

test("a pregnant cow can be confirmed pregnant again; no due date is left out of the request", async () => {
  await record("Confirm pregnant", "2026-06-01");

  assert.deepEqual(posts()[0].body, { type: "confirmed_pregnant", date: "2026-06-01", notes: null });
});

test("only confirming a pregnancy offers a due date", () => {
  for (const label of PREGNANT_BUTTONS) {
    actionButtons().find((b) => b.textContent === label).click();
    assert.equal($("#action-due-field").hidden, label !== "Confirm pregnant", label);
  }
});

test("recording a loss posts a lost event and the cow can only be bred again", async () => {
  await record("Record loss", "2026-11-12");

  assert.deepEqual(posts()[0].body, { type: "lost", date: "2026-11-12", notes: null });
  assert.equal($("#action-status").textContent, "Loss recorded.");
  assert.equal($("#event-list").children[0].textContent, "Lost pregnancy2026-11-12");
  assert.deepEqual(detailRows(), { Breeding: "Open" });
  assert.deepEqual(labels(), ["Record breeding"]);
});

test("confirming open posts a confirmed_open event and the cow can only be bred again", async () => {
  await record("Record breeding", "2026-12-01");
  await record("Confirm open", "2027-01-15");

  assert.deepEqual(posts()[0].body, { type: "confirmed_open", date: "2027-01-15", notes: null });
  assert.equal($("#event-list").children[0].textContent, "Confirmed open2027-01-15");
  assert.deepEqual(detailRows(), { Breeding: "Open" });
  assert.deepEqual(labels(), ["Record breeding"]);
});

test("recording calving posts a calved event and the cow is open", async () => {
  await record("Record breeding", "2027-02-01");
  await record("Record calving", "2027-11-10");

  // A calf is added too, with its sex not known yet.
  assert.deepEqual(posts()[0].body, { type: "calved", date: "2027-11-10", notes: null, calf: {} });
  assert.equal($("#action-status").textContent, "Calving recorded.");
  assert.equal($("#event-list").children[0].textContent, "Calved2027-11-10");
  assert.deepEqual(detailRows(), { Breeding: "Open" });
  assert.deepEqual(labels(), ["Record breeding"]);
});

test("only calving adds a calf", async () => {
  await record("Record breeding", "2028-02-01");

  assert.equal(posts()[0].body.calf, undefined);
});
