import assert from "node:assert/strict";
import { afterEach, before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

let calls = [];
let window;

before(async () => {
  const fetchStub = async (url, options = {}) => {
    const { pathname } = new URL(url);
    const method = options.method ?? "GET";
    calls.push({ method, pathname, body: options.body && JSON.parse(options.body) });

    if (method === "POST" && pathname === "/animals") {
      return jsonResponse({ id: "01NEW", ...JSON.parse(options.body) }, 201);
    }
    return jsonResponse({ animals: [] });
  };

  window = await loadPage("add.html", { fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const form = () => $("#animal-form");
const posts = () => calls.filter((c) => c.method === "POST");
const visible = (id) => !$(`#${id}-field`).hidden;

function chooseSex(sex) {
  form().elements.sex.value = sex;
  form().elements.sex.dispatchEvent(new window.Event("change", { bubbles: true }));
}

async function submit() {
  form().elements.number.value = "301";
  form().elements.date_of_birth.value = "2024-03-01";
  calls = [];
  form().requestSubmit();
  await waitFor(() => posts().length === 1, "the POST");
  await waitFor(() => $("#form-status").textContent === "Added #301.", "success message");
}

afterEach(() => {
  form().reset();
  chooseSex("female"); // the default
});

function choosePregnant() {
  form().elements.breeding_state.value = "pregnant";
  form().elements.breeding_state.dispatchEvent(new window.Event("change", { bubbles: true }));
}

test("a female is offered a breeding state but not castration", () => {
  assert.equal(visible("breeding-state"), true);
  assert.equal(visible("castrated"), false);
});

test("a male is offered only 'Already castrated'", () => {
  chooseSex("male");

  assert.equal(visible("castrated"), true);
  assert.equal(visible("breeding-state"), false);
});

test("the due date is offered only while the breeding state is pregnant", () => {
  assert.equal(visible("due-date"), false);

  choosePregnant();
  assert.equal(visible("due-date"), true);

  form().elements.breeding_state.value = "open";
  form().elements.breeding_state.dispatchEvent(new window.Event("change", { bubbles: true }));
  assert.equal(visible("due-date"), false);
});

test("a ticked flag is submitted as true", async () => {
  chooseSex("male");
  form().elements.castrated.checked = true;

  await submit();

  assert.equal(posts()[0].body.castrated, true);
});

test("a female is submitted with her breeding state, unbred by default, and no flag", async () => {
  await submit();

  assert.equal(posts()[0].body.breeding_state, "unbred");
  assert.equal("due_date" in posts()[0].body, false);
  assert.equal("castrated" in posts()[0].body, false);
});

test("a chosen breeding state is submitted", async () => {
  form().elements.breeding_state.value = "bred";

  await submit();

  assert.equal(posts()[0].body.breeding_state, "bred");
});

test("a pregnant female is submitted with her due date, if one is given", async () => {
  choosePregnant();
  form().elements.due_date.value = "2027-02-01";

  await submit();

  assert.equal(posts()[0].body.breeding_state, "pregnant");
  assert.equal(posts()[0].body.due_date, "2027-02-01");
});

test("a pregnant female may be submitted without a due date", async () => {
  choosePregnant();

  await submit();

  assert.equal("due_date" in posts()[0].body, false);
});

test("moving away from pregnant clears the due date so it is not submitted", async () => {
  choosePregnant();
  form().elements.due_date.value = "2027-02-01";
  form().elements.breeding_state.value = "open";
  form().elements.breeding_state.dispatchEvent(new window.Event("change", { bubbles: true }));

  await submit();

  assert.equal(posts()[0].body.breeding_state, "open");
  assert.equal("due_date" in posts()[0].body, false);
});

test("a male is submitted without a breeding state or due date, whatever was chosen for a female", async () => {
  choosePregnant();
  form().elements.due_date.value = "2027-02-01";
  chooseSex("male");

  await submit();

  assert.equal(posts()[0].body.sex, "male");
  assert.equal("breeding_state" in posts()[0].body, false);
  assert.equal("due_date" in posts()[0].body, false);
  assert.equal("castrated" in posts()[0].body, false);
});

test("switching sex clears the castrated tick so it is not submitted", async () => {
  chooseSex("male");
  form().elements.castrated.checked = true;
  chooseSex("female");

  await submit();

  assert.equal(form().elements.castrated.checked, false);
  assert.equal("castrated" in posts()[0].body, false);
});

test("after a successful submit the form is back to the female default", async () => {
  chooseSex("male");
  form().elements.castrated.checked = true;

  await submit();

  assert.equal(form().elements.sex.value, "female");
  assert.equal(visible("breeding-state"), true);
  assert.equal(form().elements.breeding_state.value, "unbred");
  assert.equal(visible("due-date"), false);
  assert.equal(visible("castrated"), false);
  assert.equal(form().elements.castrated.checked, false);
});
