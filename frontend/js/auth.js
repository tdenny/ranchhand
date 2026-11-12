import { getToken, setToken } from "./api.js";

// Prompt for the API token and store it. Returns false if the prompt is cancelled.
export function askForToken() {
  const token = window.prompt("Enter the API token:", getToken());
  if (token === null) return false;
  setToken(token.trim());
  return true;
}
