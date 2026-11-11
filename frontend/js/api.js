import { API_BASE_URL } from "./config.js";

const TOKEN_KEY = "ranchhand.token";

export class UnauthorizedError extends Error {}

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

async function request(path) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });

  if (response.status === 401) {
    throw new UnauthorizedError("The API rejected the token.");
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
