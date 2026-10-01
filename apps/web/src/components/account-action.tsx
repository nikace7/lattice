"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Session, type Workspace } from "@/lib/api";
import { Authentication } from "./library";
import { ErrorNotice, Loading, useAction, useResource } from "./resource";

export default function AccountAction({ kind }: { kind: "recovery" | "reset" | "invite" }) {
  const [token, setToken] = useState<string | null>(null);
  const captured = useRef(false);
  const [message, setMessage] = useState("");
  const action = useAction();
  const session = useResource<Session>("/auth/session");
  const router = useRouter();
  useEffect(() => {
    if (captured.current) return;
    captured.current = true;
    // Fragments never reach HTTP access logs. Keep the secret only in component memory.
    const secret = new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
    window.history.replaceState(null, "", window.location.pathname);
    // Sync with the external URL after hydration.
    queueMicrotask(() => setToken(secret));
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void action.run(async () => {
      if (kind === "invite") {
        const workspace = await api<Workspace>("/auth/invitations/accept", "POST", { token });
        router.replace(`/w/${workspace.id}/documents`);
      } else {
        const response = await api<{ message: string }>(`/auth/${kind}`, "POST",
          kind === "recovery" ? { email: values.get("email") } : { token, password: values.get("password") });
        setMessage(response.message);
      }
    });
  }
  if (kind === "invite" && session.data && !session.data.user)
    return <Authentication onSuccess={session.reload} invitation />;
  const title = kind === "recovery" ? "Find your way back" : kind === "reset" ? "Choose a new password" : "Join your team’s library";
  return <div className="lobby">
    <header className="topbar"><Link className="wordmark" href="/">lattice.</Link></header>
    <main id="main" tabIndex={-1} className="lobby-main">
      <div className="auth-form">
        <p className="eyebrow">YOUR ACCOUNT</p>
        <h1>{title}</h1>
        <ErrorNotice error={session.error} retry={session.reload} />
        {token === null || !session.data ? <Loading /> : message ? <>
          <p role="status">{message}</p>
          <Link href="/">Return to sign in</Link>
        </> : kind !== "recovery" && !token ? <>
          <p role="alert">This link is missing its invitation or recovery code. Open the full link from your email again.</p>
          <Link href="/account/recovery">Request a recovery link</Link>
        </> : <form onSubmit={submit}>
          {kind === "recovery" ? <>
            <p className="muted">Enter the email you used when you created your account.</p>
            <label htmlFor="recovery-email">Email address</label>
            <input id="recovery-email" name="email" type="email" autoComplete="email" maxLength={254} required disabled={action.busy} />
          </> : kind === "reset" ? <>
            <p className="muted">Use at least 8 characters. Changing your password signs out your other sessions.</p>
            <label htmlFor="new-password">New password</label>
            <input id="new-password" name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} required disabled={action.busy} />
          </> : <>
            <p className="muted">Signed in as {session.data.user?.username}. Accept to join the workspace with the role your owner selected.</p>
            <button type="button" className="text-button" disabled={action.busy} onClick={() => void action.run(async () => { await api("/auth/logout", "POST"); session.reload(); })}>Use another account</button>
          </>}
          <ErrorNotice error={action.error} />
          <button className="primary-button full-width" disabled={action.busy}>
            {action.busy ? "Please wait…" : kind === "recovery" ? "Send recovery link" : kind === "reset" ? "Save new password" : "Accept invitation"}
          </button>
        </form>}
      </div>
    </main>
  </div>;
}
