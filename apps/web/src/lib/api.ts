import type { components } from "./api.generated";

export type Session = components["schemas"]["SessionData"];
export type Workspace = components["schemas"]["WorkspaceData"];
export type Collection = components["schemas"]["CollectionData"];
export type Member = components["schemas"]["MembershipData"];
export type Grant = components["schemas"]["GrantData"];
export type DocumentSource = components["schemas"]["DocumentData"];
export type SourceBlock = components["schemas"]["BlockData"];
export type SearchResult = components["schemas"]["SearchData"];
export type Conversation = components["schemas"]["ConversationData"];
export type Turn = components["schemas"]["TurnData"];
export type SourceQuote = components["schemas"]["SourceQuoteData"];
export type AnswerCapability = components["schemas"]["AnswerCapabilityData"];
export type Page<T> = {
  results: T[];
  next: string | null;
  previous: string | null;
};
let csrfToken = "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  if (method !== "GET" && !csrfToken) await api<Session>("/auth/session");
  const response = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    signal,
    headers: {
      ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(method === "GET" ? {} : { "X-CSRFToken": csrfToken }),
    },
    ...(body === undefined ? {} : { body: body instanceof FormData ? body : JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const fields = data?.error?.fieldErrors;
    const message = fields
      ? Object.entries(fields)
          .map(([key, value]) => `${key}: ${String(value)}`)
          .join(" ")
      : data?.error?.message;
    throw new ApiError(
      response.status,
      message ?? "The server is unavailable. Please try again.",
    );
  }
  if (typeof data?.csrfToken === "string") csrfToken = data.csrfToken;
  return data as T;
}

export function nextPath(url: string | null): string | null {
  if (!url) return null;
  const next = new URL(url, window.location.origin);
  if (
    next.origin !== window.location.origin ||
    !next.pathname.startsWith("/api/v1/")
  )
    throw new Error("Unexpected pagination address.");
  return next.pathname.slice("/api/v1".length) + next.search;
}
