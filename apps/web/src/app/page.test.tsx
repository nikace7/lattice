import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Home from "./page";

afterEach(() => vi.unstubAllGlobals());

test("sign-in presents available capabilities honestly and preserves input on failure", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ user: null, csrfToken: "test-token" })),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: { message: "The username or password is incorrect." },
        }),
        { status: 401 },
      ),
    );
  vi.stubGlobal("fetch", fetchMock);
  render(<Home />);
  expect(
    await screen.findByRole("heading", { name: "Welcome back" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Search indexed documents.*Ask questions with verified source passages/),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Username"), {
    target: { value: "reader" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "incorrect" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.getByLabelText("Username")).toHaveValue("reader");
  expect(fetchMock.mock.calls[1][1].headers["X-CSRFToken"]).toBe("test-token");
});
