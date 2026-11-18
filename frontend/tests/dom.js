import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const FRONTEND_DIR = new URL("../", import.meta.url);

/**
 * Load one of the frontend pages into jsdom and run its script.
 *
 * jsdom does not run <script type="module">, so the page's script is imported
 * directly, with the DOM exposed as globals (including the classes and helpers Choices.js needs). `fetch` is replaced by `fetchStub`
 * (the code under test looks it up at call time).
 *
 * Globals and module state are shared, so each test file should load one page.
 */
export async function loadPage(page, { search = "", fetchStub, token = "test-token" } = {}) {
  const dom = new JSDOM(readFileSync(new URL(page, FRONTEND_DIR), "utf8"), {
    url: `http://localhost:8080/${page}${search}`,
    pretendToBeVisual: true, // provides requestAnimationFrame, which Choices.js uses
  });
  const { window } = dom;

  // jsdom has no matchMedia; Choices.js asks it whether the pointer is coarse.
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

  window.localStorage.setItem("ranchhand.token", token);
  Object.assign(globalThis, {
    window,
    document: window.document,
    localStorage: window.localStorage,
    FormData: window.FormData,
    fetch: fetchStub,
    requestAnimationFrame: window.requestAnimationFrame.bind(window),
    cancelAnimationFrame: window.cancelAnimationFrame.bind(window),
  });
  // Libraries that build or type-check DOM nodes need jsdom's classes. Node has its own Event and
  // CustomEvent, which jsdom's dispatchEvent rejects, so these replace the built-ins.
  for (const name of [
    "Event", "CustomEvent", "KeyboardEvent", "MouseEvent", "FocusEvent", "InputEvent",
    "Node", "Element", "HTMLElement", "HTMLInputElement", "HTMLSelectElement", "Option",
    "DocumentFragment", "MutationObserver",
  ]) {
    globalThis[name] = window[name];
  }

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
