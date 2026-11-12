import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const FRONTEND_DIR = new URL("../", import.meta.url);

/**
 * Load one of the frontend pages into jsdom and run its script.
 *
 * jsdom does not run <script type="module">, so the page's script is imported
 * directly, with the DOM exposed as globals. `fetch` is replaced by `fetchStub`
 * (the code under test looks it up at call time).
 *
 * Globals and module state are shared, so each test file should load one page.
 */
export async function loadPage(page, { fetchStub, token = "test-token" } = {}) {
  const dom = new JSDOM(readFileSync(new URL(page, FRONTEND_DIR), "utf8"), {
    url: `http://localhost:8080/${page}`,
  });
  const { window } = dom;

  window.localStorage.setItem("ranchhand.token", token);
  Object.assign(globalThis, {
    window,
    document: window.document,
    localStorage: window.localStorage,
    FormData: window.FormData,
    fetch: fetchStub,
  });

  const script = window.document.querySelector("script[type=module]").getAttribute("src");
  await import(new URL(script, FRONTEND_DIR));

  return window;
}

/** A minimal stand-in for a fetch Response. */
export function jsonResponse(body, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

/** Poll until `condition()` is truthy, since the pages render after async fetches. */
export async function waitFor(condition, message = "condition") {
  for (let i = 0; i < 50; i++) {
    if (condition()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error(`Timed out waiting for ${message}`);
}
