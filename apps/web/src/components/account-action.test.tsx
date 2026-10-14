import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { api } from "@/lib/api";
import AccountAction from "./account-action";
import { EmailVerification } from "./email-verification";

vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), api: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); window.history.replaceState(null, "", "/"); });
const signedIn = { user: { id: "reader", username: "reader", emailVerified: false }, csrfToken: "csrf" };

test("verification notice requests email only on click and permits resend after an error", async () => {
  vi.mocked(api).mockRejectedValueOnce(new Error("Wait before requesting another link."))
    .mockResolvedValueOnce({ message: "Check your email for a verification link." });
  render(<EmailVerification verified={false} />);
  expect(api).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Send verification email" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Wait before requesting another link.");
  fireEvent.click(screen.getByRole("button", { name: "Send verification email" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Check your email");
  expect(api).toHaveBeenCalledWith("/auth/verification", "POST");
  expect(screen.getByRole("button", { name: "Resend verification email" })).toBeEnabled();
});

test("verification notice is absent for verified accounts and old session responses", () => {
  const { rerender } = render(<EmailVerification verified />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  rerender(<EmailVerification />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("verification strips the fragment immediately and waits for explicit confirmation", async () => {
  window.history.replaceState(null, "", "/account/verify#token=private-code");
  vi.mocked(api).mockResolvedValue(signedIn);
  render(<AccountAction kind="verify" />);
  const confirm = await screen.findByRole("button", { name: "Verify email address" });
  expect(window.location.hash).toBe("");
  expect(api).not.toHaveBeenCalledWith("/auth/verify", expect.anything(), expect.anything());
  fireEvent.click(confirm);
  expect(await screen.findByRole("status")).toHaveTextContent("Your email address is verified.");
  expect(api).toHaveBeenCalledWith("/auth/verify", "POST", { token: "private-code" });
});

test("an invalid verification link shows the error and supports switching accounts without losing its token", async () => {
  window.history.replaceState(null, "", "/account/verify#token=account-code");
  let loggedIn = true;
  let attempts = 0;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/auth/session") return loggedIn ? signedIn : { user: null, csrfToken: "csrf" };
    if (path === "/auth/logout") { loggedIn = false; return {}; }
    if (path === "/auth/login") { loggedIn = true; return signedIn; }
    if (path === "/auth/verify" && attempts++ === 0) throw new Error("This link is invalid for this account.");
    return signedIn;
  });
  render(<AccountAction kind="verify" />);
  fireEvent.click(await screen.findByRole("button", { name: "Verify email address" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid for this account");
  fireEvent.click(screen.getByRole("button", { name: "Use another account" }));
  await screen.findByRole("heading", { name: "Welcome back" });
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "reader" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  fireEvent.click(await screen.findByRole("button", { name: "Verify email address" }));
  await screen.findByText("Your email address is verified.");
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === "/auth/verify").map(([, , body]) => body))
    .toEqual([{ token: "account-code" }, { token: "account-code" }]);
});

test("invitation tokens survive sign-in and missing verification tokens cannot be submitted", async () => {
  window.history.replaceState(null, "", "/account/invite#token=invite-code");
  let loggedIn = false;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/auth/session") return loggedIn ? signedIn : { user: null, csrfToken: "csrf" };
    if (path === "/auth/login") { loggedIn = true; return signedIn; }
    return { id: "workspace" };
  });
  const view = render(<AccountAction kind="invite" />);
  await screen.findByRole("heading", { name: "Welcome back" });
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "reader" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  fireEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("/auth/invitations/accept", "POST", { token: "invite-code" }));
  view.unmount();
  render(<AccountAction kind="verify" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("missing its verification code");
  expect(screen.queryByRole("button", { name: "Verify email address" })).not.toBeInTheDocument();
});
