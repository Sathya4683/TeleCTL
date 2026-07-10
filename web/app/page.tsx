import { WA_ME_DISPLAY_NUMBER, WA_ME_LINK, COMMANDS } from "@/lib/site";
import { QRCode } from "@/components/qr-code";

export default function Home() {
  return (
    <div className="flex flex-col flex-1">
      {/* ─── Hero ─────────────────────────────────────────────── */}
      <section className="flex flex-1 items-center justify-center px-6 py-24 bg-linear-to-b from-zinc-50 to-white dark:from-zinc-950 dark:to-black">
        <div className="max-w-3xl w-full grid sm:grid-cols-[1fr_auto] gap-12 items-center">
          <div className="flex flex-col gap-6">
            <span className="inline-block w-fit px-3 py-1 text-xs font-medium rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
              WhatsApp · v21.0
            </span>
            <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">
              Personal tooling, delivered via WhatsApp.
            </h1>
            <p className="text-lg leading-8 text-zinc-600 dark:text-zinc-400">
              DM the WACTL bot, type a slash command, attach a file — get the
              result back in chat. PDF tools, image tools, GitHub summaries,
              translation, and more. No app to install, no account to create.
            </p>
            <div className="flex flex-wrap gap-3">
              <a
                href={WA_ME_LINK}
                className="inline-flex h-12 items-center justify-center rounded-full bg-emerald-500 px-6 text-sm font-semibold text-white shadow-sm hover:bg-emerald-600 transition-colors"
              >
                Open in WhatsApp
              </a>
              <a
                href="/docs"
                className="inline-flex h-12 items-center justify-center rounded-full border border-zinc-200 px-6 text-sm font-semibold text-zinc-700 hover:bg-zinc-100 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-900 transition-colors"
              >
                Read the docs
              </a>
            </div>
          </div>
          <div className="flex flex-col items-center gap-3">
            <QRCode data={WA_ME_LINK} size={192} />
            <p className="text-xs text-zinc-500 dark:text-zinc-500">
              {WA_ME_DISPLAY_NUMBER}
            </p>
          </div>
        </div>
      </section>

      {/* ─── Commands ────────────────────────────────────────── */}
      <section className="px-6 py-20 bg-white dark:bg-black border-t border-zinc-200 dark:border-zinc-900">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">
            Commands
          </h2>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            Type a slash command in your DM. Attach a file where noted.
          </p>
          <div className="mt-8 grid sm:grid-cols-2 gap-4">
            {COMMANDS.map((cmd) => (
              <div
                key={cmd.name}
                className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-5 hover:border-emerald-500/40 transition-colors"
              >
                <code className="text-sm font-mono text-emerald-700 dark:text-emerald-400">
                  {cmd.name}
                </code>
                <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
                  {cmd.description}
                </p>
                <p className="mt-3 text-xs font-mono text-zinc-500 dark:text-zinc-500">
                  {cmd.example}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── How it works ──────────────────────────────────── */}
      <section className="px-6 py-20 bg-zinc-50 dark:bg-zinc-950 border-t border-zinc-200 dark:border-zinc-900">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">
            How it works
          </h2>
          <ol className="mt-6 space-y-4 text-sm leading-7 text-zinc-700 dark:text-zinc-300">
            <li>
              <strong className="text-zinc-950 dark:text-zinc-50">1.</strong>{" "}
              You DM the WhatsApp Business number. Meta POSTs the envelope to
              API Gateway, which invokes the webhook Lambda.
            </li>
            <li>
              <strong className="text-zinc-950 dark:text-zinc-50">2.</strong>{" "}
              The Lambda verifies the HMAC signature, dedups the WAMID via
              DynamoDB, and looks up the command in its in-process registry.
            </li>
            <li>
              <strong className="text-zinc-950 dark:text-zinc-50">3.</strong>{" "}
              Sync commands (image tools, summaries) run inline and reply in
              the same request. Async commands (PDF→DOCX, audio) are
              enqueued to SQS — an EC2 worker picks them up and replies when
              done.
            </li>
            <li>
              <strong className="text-zinc-950 dark:text-zinc-50">4.</strong>{" "}
              Outgoing replies go straight from the worker/Lambda to the
              WhatsApp Cloud API — never back through API Gateway.
            </li>
          </ol>
        </div>
      </section>

      {/* ─── Footer ──────────────────────────────────────── */}
      <footer className="px-6 py-10 border-t border-zinc-200 dark:border-zinc-900">
        <div className="max-w-4xl mx-auto flex flex-wrap justify-between gap-4 text-xs text-zinc-500">
          <p>
            WACTL · Open-source WhatsApp automation. See{" "}
            <a href="/privacy" className="underline">
              privacy
            </a>{" "}
            and{" "}
            <a href="/terms" className="underline">
              terms
            </a>
            .
          </p>
          <p>
            <a
              href="https://github.com/sathya-narayanan/wactl"
              className="underline"
            >
              Source
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}