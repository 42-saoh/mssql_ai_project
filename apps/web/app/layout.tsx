import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "MSSQL Agent Portal",
  description: "Central portal shell for MSSQL analysis, documentation, and draft generation."
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>
        <header className="app-header">
          <Link className="brand" href="/">
            <span>MSSQL Agent Portal</span>
          </Link>
          <nav aria-label="Primary navigation">
            <Link href="/requests/new">New request</Link>
            <Link href="/jobs">Analysis history</Link>
            <Link href="/metadata/search">Metadata search</Link>
            <Link href="/metadata/design">Metadata design</Link>
            <Link href="/metadata/dependencies">Dependency diagnostics</Link>
          </nav>
        </header>
        <main className="app-main">{children}</main>
      </body>
    </html>
  );
}
