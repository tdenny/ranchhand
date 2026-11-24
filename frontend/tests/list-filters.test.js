import assert from "node:assert/strict";
import { test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

const HERD = [
  { id: "1", number: "1", sex: "female", status: "active", category: "Cow", breeding_state: "open" },
  { id: "2", number: "2", sex: "female", status: "active", category: "Cow", breeding_state: "pregnant" },
  { id: "3", number: "3", sex: "female", status: "active", category: "Heifer calf", breeding_state: "unbred" },
  { id: "4", number: "4", sex: "male", status: "active", category: "Bull calf", breeding_state: null },
  { id: "5", number: "5", sex: "male", status: "active", category: "Steer", breeding_state: null },
  { id: "6", number: "6", sex: "male", status: "active", category: null, breeding_state: null },
];

test("the quick filter buttons limit the list, All restores it, and an empty result says so", async () => {
  const fetchStub = async () => jsonResponse({ animals: HERD });
  const window = await loadPage("index.html", { fetchStub, token: "secret" });
  const { document } = window;
  const numbers = () => [...document.querySelectorAll("#animal-list a.number")].map((a) => a.textContent);
  const press = (label) => {
    [...document.querySelectorAll("#filters button")].find((b) => b.textContent === label).click();
  };
  await waitFor(() => numbers().length === HERD.length, "animal cards");

  assert.deepEqual(
    [...document.querySelectorAll("#filters button")].map((b) => b.textContent),
    ["All", "Calves", "Open cows", "Pregnant cows", "Steers"],
  );

  press("Calves");
  assert.deepEqual(numbers(), ["#3", "#4"]);
  press("Open cows");
  assert.deepEqual(numbers(), ["#1"]);
  press("Pregnant cows");
  assert.deepEqual(numbers(), ["#2"]);
  press("Steers");
  assert.deepEqual(numbers(), ["#5"]);
  assert.equal(document.querySelector("#filters [aria-pressed=true]").textContent, "Steers");
  press("All");
  assert.equal(numbers().length, HERD.length);
});
