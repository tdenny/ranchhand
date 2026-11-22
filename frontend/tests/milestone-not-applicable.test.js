import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

const COW = {
  id: "01COW", number: "101", sex: "female", status: "active", date_of_birth: "2020-04-01",
  castrated: false, bred: false, category: "Heifer",
};
let window;

before(async () => {
  const fetchStub = async (url) => {
    const { pathname } = new URL(url);
    if (pathname === "/animals/01COW") return jsonResponse(COW);
    if (pathname === "/animals/01COW/events") return jsonResponse({ events: [] });
    return jsonResponse({ message: "Not found" }, 404);
  };
  window = await loadPage("animal.html", { search: "?id=01COW", fetchStub });
});

test("a female has no Record castration button", async () => {
  await waitFor(() => !window.document.querySelector("#profile").hidden, "the profile");

  assert.equal(window.document.querySelectorAll("#milestone-actions button").length, 0);
  assert.equal(window.document.querySelector("#milestone-form").hidden, true);
});
