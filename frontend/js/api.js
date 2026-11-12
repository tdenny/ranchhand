import { API_BASE_URL } from "./config.js";

const TOKEN_KEY = "ranchhand.token";

export class UnauthorizedError extends Error {}

export class ValidationError extends Error {
  constructor(errors) {
    super("The API rejected the animal.");
    // Each entry has `loc` (e.g. ["body", "number"]) and `msg`.
    this.errors = errors;
  }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage unavailable (e.g. private mode); the token only lasts until reload.
  }
}

async function request(path, { method = "GET", body } = {}) {
  const headers = { Authorization: `Bearer ${getToken()}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401) {
    throw new UnauthorizedError("The API rejected the token.");
  }
  if (response.status === 400) {
    const { errors = [] } = await response.json().catch(() => ({}));
    throw new ValidationError(errors);
  }
  if (!response.ok) {
    throw new Error(`Request failed (HTTP ${response.status}).`);
  }
  return response.json();
}

export async function listAnimals() {
  const { animals } = await request("/animals");
  return animals;
}

export function createAnimal(animal) {
  return request("/animals", { method: "POST", body: animal });
}
