// Staff token handling. The token lives in sessionStorage (cleared when the tab closes).
const TOKEN_KEY = "urbantwin.staffToken";
const NAME_KEY = "urbantwin.staffName";

function read(key: string): string {
  try {
    return sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

export function getStaffToken(): string {
  return read(TOKEN_KEY);
}

export function getStaffName(): string {
  return read(NAME_KEY);
}

export function setStaffSession(token: string, name: string): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.setItem(NAME_KEY, name);
  } catch {
    /* storage blocked: the token simply will not persist */
  }
  window.dispatchEvent(new Event("urbantwin-auth"));
}

/** fetch() that adds the staff headers and announces 401s so the header can prompt for login. */
function problem(message: string): void {
  window.dispatchEvent(new CustomEvent("urbantwin-problem", { detail: message }));
}

export async function apiFetch(input: string, init: RequestInit = {}, opts: { quiet?: boolean } = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getStaffToken();
  if (token) headers.set("X-Staff-Token", token);
  const name = getStaffName();
  if (name) headers.set("X-Staff-Name", name);
  let response: Response;
  try {
    response = await fetch(input, { ...init, headers });
  } catch (error) {
    if (!opts.quiet && (error as Error).name !== "AbortError") problem("Cannot reach the server. Check that the API is running and your connection is up, then try again.");
    throw error;
  }
  if (response.status === 401) window.dispatchEvent(new Event("urbantwin-unauthorized"));
  else if (response.status >= 500 && !opts.quiet) problem(`The server hit a problem (error ${response.status}). Try again; if it keeps happening, check the API log.`);
  return response;
}

export async function apiJson<T>(input: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(input, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = (body as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return body as T;
}

export const money = (value: number | null | undefined): string =>
  value == null ? "–" : `${Math.round(value).toLocaleString("en-US")} BDT`;
