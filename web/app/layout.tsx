import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "WACTL — Personal tooling via WhatsApp",
  description:
    "DM the WACTL bot with a slash command, get the result back in chat. PDF tools, image tools, GitHub summaries, translation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <nav className="border-b border-zinc-200 dark:border-zinc-900 px-6 py-4">
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <Link
              href="/"
              className="text-sm font-semibold tracking-tight text-zinc-950 dark:text-zinc-50"
            >
              WACTL
            </Link>
            <ul className="flex items-center gap-6 text-sm text-zinc-600 dark:text-zinc-400">
              <li>
                <Link
                  href="/docs"
                  className="hover:text-zinc-950 dark:hover:text-zinc-50"
                >
                  Docs
                </Link>
              </li>
              <li>
                <Link
                  href="/privacy"
                  className="hover:text-zinc-950 dark:hover:text-zinc-50"
                >
                  Privacy
                </Link>
              </li>
              <li>
                <Link
                  href="/terms"
                  className="hover:text-zinc-950 dark:hover:text-zinc-50"
                >
                  Terms
                </Link>
              </li>
            </ul>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}