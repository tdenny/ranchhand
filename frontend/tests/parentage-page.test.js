import assert from "node:assert/strict";
import { before, test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

// An external animal (no date of birth) whose sire resolves and whose dam can't be found.
const ANIMAL = {
  id: "01AAA", number: "Straw 7", sex: "male", status: "external", date_of_birth: null,
  sire_id: "01SIRE", dam_id: "01DAM",
};
const SIRE = { id: "01SIRE", number: "201", sex: "male", status: "deceased", date_of_birth: "2015-02-10" };

let window;

before(async () => {
  const fetchStub = async (url) => {
    const { pathname } = new URL(url);
    if (pathname === "/animals/01AAA") return jsonResponse(ANIMAL);
    if (pathname === "/animals/01AAA/events") return jsonResponse({ events: [] });
    if (pathname === "/animals/01SIRE") return jsonResponse(SIRE);
    return jsonResponse({ message: "Not found" }, 404);
  };
  window = await loadPage("animal.html", { search: "?id=01AAA", fetchStub });
});

const details = () => {
  const dts = [...window.document.querySelectorAll("#profile-details dt")];
  const dds = [...window.document.querySelectorAll("#profile-details dd")];
  return Object.fromEntries(dts.map((dt, i) => [dt.textContent, dds[i]]));
};

test("an unknown date of birth reads Unknown, not null", async () => {
  await waitFor(() => details()["Date of birth"], "profile");
  assert.equal(details()["Date of birth"].textContent, "Unknown");
});

test("the sire is a link to its detail page, labelled by number", async () => {
  await waitFor(() => details().Sire?.querySelector("a"), "sire link");
  const link = details().Sire.querySelector("a");
  assert.equal(link.textContent, "#201");
  assert.equal(link.getAttribute("href"), "animal.html?id=01SIRE");
});

test("a parent that can't be found is reported without hiding the rest", async () => {
  await waitFor(() => details().Dam?.textContent === "Not found", "dam row");
  assert.equal(details().Status.textContent, "external");
});
