import assert from "node:assert/strict";
import { afterEach, before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

const ALL_STATUSES = ["active", "deceased", "processed", "sold", "external"];

const candidates = [
  { id: "01BULL1", number: "201", sex: "male", status: "active", date_of_birth: "2018-03-01" },
  { id: "01BULL2", number: "202", sex: "male", status: "deceased", date_of_birth: "2015-02-10" },
  { id: "01EXT1", number: "Black Jack", sex: "male", status: "external", date_of_birth: null },
  { id: "01COW1", number: "101", sex: "female", status: "active", date_of_birth: "2020-04-01" },
  { id: "01COW2", number: "102", sex: "female", status: "sold", date_of_birth: "2019-05-06" },
];

let calls;
let failCandidates = false;
let window;

// The page and its script load once per file, so the tests below share it and run in order:
// the first one sees the candidates fetched, and a later one sees them fetched again.
before(async () => {
  calls = [];
  const fetchStub = async (url, options = {}) => {
    const { pathname, searchParams } = new URL(url);
    const method = options.method ?? "GET";
    const statuses = searchParams.getAll("status");
    calls.push({ method, pathname, statuses, body: options.body && JSON.parse(options.body) });

    if (method === "GET" && pathname === "/animals") {
      if (statuses.length && failCandidates) return jsonResponse({ message: "boom" }, 500);
      // Mirror the API: no filter means everything but external animals.
      const wanted = statuses.length ? statuses : ALL_STATUSES.filter((s) => s !== "external");
      return jsonResponse({ animals: candidates.filter((a) => wanted.includes(a.status)) });
    }
    if (method === "POST" && pathname === "/animals") {
      const animal = { id: "01NEW", ...JSON.parse(options.body) };
      candidates.push(animal);
      return jsonResponse(animal, 201);
    }
    return jsonResponse({ message: "Not found" }, 404);
  };

  window = await loadPage("index.html", { fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const form = () => $("#animal-form");
const field = (name) => $(`#${name}`); // the <select> that carries the value
const box = (name) => field(name).closest(".choices"); // the widget Choices builds around it
const tick = (ms = 30) => new Promise((resolve) => setTimeout(resolve, ms));
const candidateCalls = () => calls.filter((c) => c.method === "GET" && c.statuses.length);
const posts = () => calls.filter((c) => c.method === "POST");

function options(name) {
  return [...box(name).querySelectorAll(".choices__list--dropdown [role=option]")].map((el) => ({
    value: el.dataset.value,
    label: el.firstChild.textContent.trim(),
    description: el.querySelector(".choices__description")?.textContent ?? null,
    placeholder: el.classList.contains("choices__placeholder"),
  }));
}

/** The numbers on offer, leaving out the "None" entry that clears the pick. */
const numbers = (name) => options(name).filter((o) => !o.placeholder).map((o) => o.label);

const shown = (name) => box(name).querySelector(".choices__list--single").textContent.trim();

/** Open a picker and wait for the list to be built; Choices fills it a frame after the click. */
async function openPicker(name) {
  box(name).click();
  await waitFor(() => box(name).classList.contains("is-open"), `${name} picker to open`);
}

/** Poll until `read()` equals `expected`, then assert it, so a failure shows the actual value. */
async function eventually(read, expected) {
  for (let i = 0; i < 100 && JSON.stringify(read()) !== JSON.stringify(expected); i++) await tick(10);
  assert.deepEqual(read(), expected);
}

async function search(name, text) {
  const input = box(name).querySelector("input[type=search]");
  input.value = text;
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
  await tick();
}

function pick(name, value) {
  const option = box(name).querySelector(`.choices__list--dropdown [data-value="${value}"]`);
  option.dispatchEvent(new window.MouseEvent("mousedown", { bubbles: true, cancelable: true }));
}

async function closePickers() {
  window.document.body.click(); // a click outside closes any open dropdown
  await tick();
}

function fillRequiredFields() {
  form().elements.number.value = "301";
  form().elements.date_of_birth.value = "2024-03-01";
}

afterEach(async () => {
  await closePickers();
  form().reset();
  await tick();
});

test("opening a picker fetches every status once, shared by both, and offers only the right sex", async () => {
  assert.equal(candidateCalls().length, 0, "nothing is fetched for the pickers until one is opened");

  await openPicker("sire");
  await eventually(() => numbers("sire"), ["#201", "#202", "#Black Jack"]);
  await closePickers();

  await openPicker("dam");
  await eventually(() => numbers("dam"), ["#101", "#102"]);

  assert.equal(candidateCalls().length, 1);
  assert.deepEqual(candidateCalls()[0].statuses, ALL_STATUSES);
});

test("each option shows its status and birth date, with a missing birth date called out", async () => {
  await openPicker("sire");

  await eventually(
    () => options("sire").filter((o) => !o.placeholder).map((o) => o.description),
    ["active · born 2018-03-01", "deceased · born 2015-02-10", "external · born unknown"],
  );
});

test("search matches part of the number, ignoring case, and never fuzzily or on the id", async () => {
  await openPicker("sire");
  await eventually(() => numbers("sire").length, 3);

  await search("sire", "202");
  await eventually(() => numbers("sire"), ["#202"]); // #201 is one typo away but isn't a match

  await search("sire", "20");
  await eventually(() => numbers("sire"), ["#201", "#202"]);

  await search("sire", "BLACK");
  await eventually(() => numbers("sire"), ["#Black Jack"]);

  await search("sire", "01BULL"); // ids are not searchable
  await eventually(() => numbers("sire"), []);
  assert.match(box("sire").textContent, /No matching animals/);
});

test("picking an animal shows its number and puts its id in the form field", async () => {
  await openPicker("sire");
  await eventually(() => numbers("sire").length, 3);
  pick("sire", "01BULL2");
  await tick();

  assert.equal(field("sire").value, "01BULL2");
  assert.equal(shown("sire"), "#202");
  assert.equal(new window.FormData(form()).get("sire_id"), "01BULL2");
  assert.ok(!box("sire").classList.contains("is-open"), "the list closes after a pick");
});

test("choosing None clears a pick, and reopening the list doesn't duplicate the picked animal", async () => {
  await openPicker("dam");
  await eventually(() => numbers("dam").length, 2);
  pick("dam", "01COW1");
  await tick();

  await openPicker("dam");
  await eventually(() => numbers("dam"), ["#101", "#102"]);

  pick("dam", "");
  await tick();
  assert.equal(field("dam").value, "");
  assert.equal(shown("dam"), "None");
});

test("submitting sends the picked ids, the form then resets, and a new animal becomes pickable", async () => {
  await openPicker("sire");
  await eventually(() => numbers("sire").length, 3);
  pick("sire", "01BULL1");
  await tick();
  await openPicker("dam");
  await eventually(() => numbers("dam").length, 2);
  pick("dam", "01COW1");
  await tick();
  fillRequiredFields();
  calls = [];

  form().requestSubmit();
  await waitFor(() => posts().length === 1, "the POST");
  await waitFor(() => $("#form-status").textContent === "Added #301.", "success message");
  await tick(50);

  assert.equal(posts()[0].body.sire_id, "01BULL1");
  assert.equal(posts()[0].body.dam_id, "01COW1");
  assert.equal(field("sire").value, "", "the pickers are reset with the form");
  assert.equal(shown("sire"), "None");

  await openPicker("dam");
  await eventually(() => numbers("dam"), ["#101", "#102", "#301"]);
  assert.equal(candidateCalls().length, 1, "the candidates are fetched again after an animal is added");
});

test("leaving both parents unpicked submits empty ids", async () => {
  fillRequiredFields();
  calls = [];

  form().requestSubmit();
  await waitFor(() => posts().length === 1, "the POST");

  assert.equal(posts()[0].body.sire_id, "");
  assert.equal(posts()[0].body.dam_id, "");
});

test("a failed load shows an error in the list, and the next open tries again", async () => {
  // The previous test added an animal without opening a picker, so the candidates are stale.
  failCandidates = true;
  await openPicker("sire");
  await eventually(() => numbers("sire"), ["Could not load animals. Request failed (HTTP 500)."]);
  assert.ok(box("sire").querySelector(".choices__list--dropdown .choices__item--disabled"), "it can't be picked");
  await closePickers();

  failCandidates = false;
  await openPicker("sire");
  await eventually(() => numbers("sire"), ["#201", "#202", "#Black Jack"]);
});
