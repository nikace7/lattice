"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, nextPath } from "@/lib/api";

export function useResource<T>(path: string) {
  const [version, setVersion] = useState(0);
  const key = `${path}:${version}`;
  const [result, setResult] = useState<{
    key: string;
    data?: T;
    error?: Error;
  }>();
  useEffect(() => {
    const controller = new AbortController();
    api<T>(path, "GET", undefined, controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ key, data });
      },
      (error: Error) => {
        if (!controller.signal.aborted) setResult({ key, error });
      },
    );
    return () => controller.abort();
  }, [path, key]);
  const reload = useCallback(() => setVersion((n) => n + 1), []);
  return {
    data: result?.key === key ? result.data : undefined,
    error: result?.key === key ? result.error : undefined,
    reload,
  };
}

export function useAction() {
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  async function run(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(undefined);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("Please try again."));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return { busy, error, run };
}

export function ErrorNotice({
  error,
  retry,
}: {
  error?: Error;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="error-notice" role="alert">
      <p>{error.message}</p>
      {retry && (
        <button type="button" className="text-button" onClick={retry}>
          Try again
        </button>
      )}
      {error instanceof ApiError && [401, 403, 404].includes(error.status) && (
        <Link href="/">Return to workspaces</Link>
      )}
    </div>
  );
}

export function Loading({
  children = "Opening your library…",
}: {
  children?: ReactNode;
}) {
  return (
    <p className="loading" role="status">
      {children}
    </p>
  );
}

export function Pagination({
  page,
  onPage,
}: {
  page: { next: string | null; previous: string | null };
  onPage: (path: string) => void;
}) {
  if (!page.next && !page.previous) return null;
  return (
    <nav aria-label="Page navigation" className="pagination">
      <button
        type="button"
        disabled={!page.previous}
        onClick={() => {
          const path = nextPath(page.previous);
          if (path) onPage(path);
        }}
      >
        Previous
      </button>
      <button
        type="button"
        disabled={!page.next}
        onClick={() => {
          const path = nextPath(page.next);
          if (path) onPage(path);
        }}
      >
        Next
      </button>
    </nav>
  );
}
