"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { ErrorNotice, useAction } from "./resource";

export function EmailVerification({ verified }: { verified?: boolean }) {
  const [message, setMessage] = useState("");
  const action = useAction();
  if (verified !== false) return null;
  return <section className="phase-note" aria-label="Email verification">
    <div>
      <strong>Confirm your email address</strong>
      <p>You can keep using your workspace. Verify your email to confirm it belongs to you.</p>
      <button type="button" disabled={action.busy} onClick={() => void action.run(async () => {
        const result = await api<{ message: string }>("/auth/verification", "POST");
        setMessage(result.message);
      })}>
        {action.busy ? "Sending…" : message ? "Resend verification email" : "Send verification email"}
      </button>
      {message && <p role="status">{message}</p>}
      <ErrorNotice error={action.error} />
    </div>
  </section>;
}
