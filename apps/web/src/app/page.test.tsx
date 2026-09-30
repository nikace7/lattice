import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home from "./page";

test("starter clearly distinguishes planned features from available capabilities", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { name: "A place for knowledge. And its sources." })).toBeInTheDocument();
  expect(screen.getByText("Project foundation")).toBeInTheDocument();
  expect(screen.getByText(/Uploads, search, and cited answers are not available yet/)).toBeInTheDocument();
});
