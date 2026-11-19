import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

const EXISTING = { id: "01XXX", number: "Big Bull", sex: "male", status: "external", date_of_birth: null };

const calls = [];
let window;
let failCreate = false;

before(async () => {
  const fetchStub = async (url, options = {}) => {
    const { pathname, search } = new URL(url);
    const method = options.method ?? "GET";
    calls.push({ method, pathname, search, body: options.body && JSON.parse(options.body) });

    if (method === "GET" && pathname === "/animals") return jsonResponse({ animals: [EXISTING] });
    if (method === "POST" && pathname === "/animals") {
      if (failCreate) return jsonResponse({ errors: [{ loc: ["body", "number"], msg: "bad" }] }, 400);
      return jsonResponse({ id: "01NEW", ...JSON.parse(options.body) }, 201);
    }
    return jsonResponse({ message: "Not found" }, 404);
  };

  window = await loadPage("external.html", { fetchStub });
});

const $ = (selector) => window.document.querySelector(selector);
const items = () => [...window.document.querySelectorAll("#animal-list li")];

function submit(number, sex) {
  const form = $("#external-form");
  form.elements.number.value = number;
  form.elements.sex.value = sex;
  form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
}

test("the page lists only external animals", async () => {
  await waitFor(() => items().length === 1, "list");
  assert.equal(calls[0].search, "?status=external");
  assert.equal(items()[0].textContent, "Big Bullsire");
});

test("adding posts an external animal with the trimmed name and chosen sex", async () => {
  submit("  Straw 42 ", "female");
  await waitFor(() => items().length === 2, "new item");

  const post = calls.find(({ method }) => method === "POST");
  assert.deepEqual(post.body, { number: "Straw 42", sex: "female", status: "external" });
  assert.equal(items()[1].textContent, "Straw 42dam");
  assert.equal($("#form-status").textContent, "Added Straw 42.");
  assert.equal($("#external-form").elements.number.value, "");
});

test("a rejected request shows the API's message and keeps the form", async () => {
  failCreate = true;
  submit("X", "male");
  await waitFor(() => $("#form-status").classList.contains("error"), "error");

  assert.equal($("#form-status").textContent, "number: bad");
  assert.equal($("#external-form").elements.number.value, "X");
  assert.equal(items().length, 2);
});
