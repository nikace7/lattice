import type { Metadata } from "next";
import { connection } from "next/server";
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "@fontsource/source-serif-4/400.css";
import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-devanagari/600.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lattice — Cited knowledge workspace",
  description:
    "A shared library for your team's knowledge and the sources behind it.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Each document must render with its own CSP nonce, never a cached build-time nonce.
  await connection();
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
