import type { Metadata } from "next";
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/600.css";
import "@fontsource/source-serif-4/400.css";
import "@fontsource/noto-sans-devanagari/400.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lattice — Cited knowledge workspace",
  description: "A workspace for knowledge and the sources behind it. Project foundation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">Skip to content</a>
        {children}
      </body>
    </html>
  );
}
