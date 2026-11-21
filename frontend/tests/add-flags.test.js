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

test("a female is offered only 'Already bred'", () => {
  assert.equal(visible("bred"), true);
  assert.equal(visible("castrated"), false);
});

test("a male is offered only 'Already castrated'", () => {
  chooseSex("male");

  assert.equal(visible("castrated"), true);
  assert.equal(visible("bred"), false);
});

test("a ticked flag is submitted as true", async () => {
  form().elements.bred.checked = true;

  await submit();

  assert.equal(posts()[0].body.bred, true);
  assert.equal("castrated" in posts()[0].body, false);
});

test("unticked flags are left out of the request", async () => {
  await submit();

  assert.equal("bred" in posts()[0].body, false);
  assert.equal("castrated" in posts()[0].body, false);
});

test("switching sex clears the other sex's tick so it is not submitted", async () => {
  form().elements.bred.checked = true;
  chooseSex("male");

  await submit();

  assert.equal(posts()[0].body.sex, "male");
  assert.equal("bred" in posts()[0].body, false);
  assert.equal(form().elements.bred.checked, false);
});

test("after a successful submit the form is back to the female default", async () => {
  chooseSex("male");
  form().elements.castrated.checked = true;

  await submit();

  assert.equal(form().elements.sex.value, "female");
  assert.equal(visible("bred"), true);
  assert.equal(visible("castrated"), false);
  assert.equal(form().elements.castrated.checked, false);
});
