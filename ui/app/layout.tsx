import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Helix",
  description: "Local DSPy compile/eval job runner",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">helix</Link>
          <nav>
            <Link href="/">jobs</Link>
            {/* Langfuse runs on its own loopback origin in v1 (no Caddy
                subpath rewrite). Link to the absolute origin so the tab
                doesn't 404. */}
            <a href="http://127.0.0.1:3010" target="_blank" rel="noreferrer">langfuse</a>
            <a href="/api/docs" target="_blank" rel="noreferrer">api</a>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
