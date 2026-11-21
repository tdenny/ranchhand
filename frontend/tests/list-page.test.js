import assert from "node:assert/strict";
import { test } from "node:test";

import { jsonResponse, loadPage, waitFor } from "./dom.js";

const ANIMALS = [
  { id: "01AAA", number: "101", sex: "female", status: "active", date_of_birth: "2022-04-01", category: "Cow" },
  { id: "01BBB", number: "102", sex: "male", status: "sold", date_of_birth: "2023-05-06", category: "Steer" },
  // No date of birth means no category, so the sex stands in.
  { id: "01CCC", number: "Black Jack", sex: "male", status: "external", date_of_birth: null, category: null },
];

test("the list page fetches animals with the token and renders a linked card for each", async () => {
  const calls = [];
  const fetchStub = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse({ animals: ANIMALS });
  };

  const window = await loadPage("index.html", { fetchStub, token: "secret" });
  const cards = () => [...window.document.querySelectorAll("#animal-list li")];
  await waitFor(() => cards().length === ANIMALS.length, "animal cards");

  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/animals$/);
  assert.equal(calls[0].options.headers.Authorization, "Bearer secret");

  assert.deepEqual(
    cards().map((card) => card.textContent),
    [
      "#101Cow · active · born 2022-04-01",
      "#102Steer · sold · born 2023-05-06",
      "#Black Jackmale · external · born unknown",
    ],
  );
  assert.deepEqual(
    cards().map((card) => card.querySelector("a").getAttribute("href")),
    ["animal.html?id=01AAA", "animal.html?id=01BBB", "animal.html?id=01CCC"],
  );
  assert.equal(window.document.querySelector("#status").textContent, "");
});
