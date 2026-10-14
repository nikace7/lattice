"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, type Session } from "@/lib/api";
import { Brand } from "./brand";
import { ErrorNotice, useAction } from "./resource";

export function Authentication({ onSuccess, invitation = false, verification = false }: { onSuccess: () => void; invitation?: boolean; verification?: boolean }) {
  const [register, setRegister] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const action = useAction();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void action.run(async () => {
      await api<Session>(`/auth/${register ? "register" : "login"}`, "POST", {
        username: values.get("username"),
        password: values.get("password"),
        ...(register ? { email: values.get("email") } : {}),
      });
      onSuccess();
    });
  }
  return (
    <div className="auth-layout">
      <section className="auth-story" aria-label="About Lattice">
        <Brand />
        <div>
          <p className="eyebrow">A shared knowledge workspace</p>
          <h2>
            Answers begin
            <br />with a source.
          </h2>
          <p>
            Bring your team’s documents together. Find the passage you need.
            Keep the evidence within reach.
          </p>
        </div>
        <ol className="auth-workflow"><li><span>01</span><div><strong>Build your library</strong><small>Private collections for your team’s documents.</small></div></li><li><span>02</span><div><strong>Find the right passage</strong><small>Search by words or meaning.</small></div></li><li><span>03</span><div><strong>Read the evidence</strong><small>Open the original source behind a citation.</small></div></li></ol>
      </section>
      <main id="main" tabIndex={-1} className="auth-main">
        <div className="auth-form">
          <p className="eyebrow">Your library awaits</p>
          <h1>{register ? "Create your account" : "Welcome back"}</h1>
          <p className="muted">
            {verification ? "Sign in to the account whose email you are verifying. Your verification link will stay here while you sign in." : invitation ? "Use the email address that received your invitation. You can accept it after signing in." : register
              ? "Start a library of your own, or join your team."
              : "Sign in to return to your workspace."}
          </p>
          <form onSubmit={submit}>
            {register && <>
              <label htmlFor="email">Email address</label>
              <input id="email" name="email" type="email" autoComplete="email" required maxLength={254} disabled={action.busy} />
            </>}
            <label htmlFor="username">Username</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              maxLength={150}
              required
              disabled={action.busy}
            />
            <label htmlFor="password">Password</label>
            <div className="password-field"><input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete={register ? "new-password" : "current-password"}
              minLength={register ? 8 : undefined}
              maxLength={128}
              required
              disabled={action.busy}
            /><button type="button" disabled={action.busy} aria-pressed={showPassword} aria-controls="password" onClick={() => setShowPassword(!showPassword)}>{showPassword ? "Hide password" : "Show password"}</button></div>
            {register && (
              <p className="field-note">
                Use at least 8 characters and avoid common passwords.
              </p>
            )}
            <ErrorNotice error={action.error} />
            <button
              className="primary-button full-width"
              disabled={action.busy}
            >
              {action.busy
                ? "Please wait…"
                : register
                  ? "Create account"
                  : "Sign in"}
            </button>
          </form>
          {!register && <p><Link href="/account/recovery">Forgot your password?</Link></p>}
          <p className="switch-auth">
            {register ? "Already have an account?" : "New to Lattice?"}{" "}
            <button
              className="text-button"
              disabled={action.busy}
              onClick={() => setRegister(!register)}
            >
              {register ? "Sign in instead" : "Create an account"}
            </button>
          </p>
          <p className="release-note">
            Early access · Search indexed documents and inspect their sources.
            Ask questions with verified source passages when local generation is configured.
          </p>
        </div>
      </main>
    </div>
  );
}
