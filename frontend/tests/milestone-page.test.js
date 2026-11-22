import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

// The API state: recording a castration flips the flag, as the real transaction does.
let animal = {
  id: "01BULL", number: "201", sex: "male", status: "active", date_of_birth: "2020-04-01",
  castrated: false, bred: false, category: "Bull",
};
let failNextPost = false;
let calls = [];
let window;

before(async () => {
  const fetchStub = async (url, options = {}) => {
    const { pathname } = new URL(url);
    const method = options.method ?? "GET";
    calls.push({ method, pathname, body: options.body && JSON.parse(options.body) });

    if (method === "GET" && pathname === "/animals/01BULL") return jsonResponse(animal);
    if (method === "GET" && pathname === "/animals/01BULL/events") return jsonResponse({ events: [] });
    if (method === "POST" && pathname === "/animals/01BULL/events") {
      if (failNextPost) {
        failNextPost = false;
        return jsonResponse({ errors: [{ loc: ["body", "type"], msg: "Only male animals can be castrated" }] }, 400);
      }
      animal = { ...animal, castrated: true, category: "Steer" };
      return jsonResponse({ id: "01E1", animal_id: "01BULL", ...JSON.parse(options.body) }, 201);
    }
    return jsonResponse({ message: "Not found" }, 404);
  };

  window = await loadPage("animal.html", { search: "?id=01BULL", fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const actionButtons = () => [...window.document.querySelectorAll("#milestone-actions button")];
const posts = () => calls.filter((c) => c.method === "POST");
const profile = () => {
  const dts = [...window.document.querySelectorAll("#profile-details dt")];
  const dds = [...window.document.querySelectorAll("#profile-details dd")];
  return Object.fromEntries(dts.map((dt, i) => [dt.textContent, dds[i].textContent]));
};

test("an uncastrated male gets a Record castration button, and the form stays closed until it is clicked", async () => {
  await waitFor(() => actionButtons().length, "the action button");

  assert.deepEqual(actionButtons().map((b) => b.textContent), ["Record castration"], "no breeding or calving for a male");
  assert.equal($("#milestone-form").hidden, true);
  assert.equal(profile().Category, "Bull");
});

test("clicking the button opens the form with today's date, and Cancel closes it without saving", () => {
  actionButtons()[0].click();

  assert.equal($("#milestone-form").hidden, false);
  assert.equal($("#milestone-title").textContent, "Record castration");
  assert.equal($("#milestone-form").elements.date.value, new Date().toLocaleDateString("en-CA"));

  $("#milestone-cancel").click();

  assert.equal($("#milestone-form").hidden, true);
  assert.equal(posts().length, 0);
});

test("a rejected request shows the API's message and keeps the form open", async () => {
  actionButtons()[0].click();
  failNextPost = true;

  $("#milestone-form").requestSubmit();
  await waitFor(() => $("#milestone-status").classList.contains("error"), "the error");

  assert.match($("#milestone-status").textContent, /Only male animals can be castrated/);
  assert.equal($("#milestone-form").hidden, false);
  assert.equal(actionButtons().length, 1);
  assert.equal($("#event-list").children.length, 0);
});

test("saving posts the castration, adds it to the events, and shows the animal as a Steer", async () => {
  const form = $("#milestone-form");
  form.elements.date.value = "2026-11-01";
  form.elements.notes.value = "  banded  ";
  calls = [];

  form.requestSubmit();
  await waitFor(() => $("#milestone-status").textContent === "Castration recorded.", "success message");

  assert.deepEqual(posts()[0].body, { type: "castrated", date: "2026-11-01", notes: "banded" });
  assert.equal($("#event-list").children[0].textContent, "Castrated2026-11-01banded");
  assert.equal(profile().Category, "Steer");
  assert.equal(actionButtons().length, 0, "an animal that is already castrated cannot be castrated again");
  assert.equal(form.hidden, true);
});
