import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { CommandMenu } from "./command-menu";

afterEach(cleanup);

test("navigation filters destinations and keeps owner tools out of viewer navigation", () => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) { this.setAttribute("open", ""); });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) { this.removeAttribute("open"); });
  render(<CommandMenu workspace={{ id: "w", name: "Studio", role: "VIEWER", revision: 1, accessEpoch: 1 }} />);
  fireEvent.click(screen.getByRole("button", { name: /Quick navigation/ }));
  expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalled();
  expect(screen.queryByText("People & access")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Find a destination"), { target: { value: "sources" } });
  expect(screen.getByRole("link", { name: /Documents/ })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Collections/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Find a destination"), { target: { value: "zzzz" } });
  expect(screen.getByRole("status")).toHaveTextContent("No destinations");
});
