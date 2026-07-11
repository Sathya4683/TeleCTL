import { COMMANDS, WA_ME_LINK } from "@/lib/site";

export const metadata = {
  title: "Docs — WACTL",
  description: "Full command reference for the WACTL WhatsApp bot.",
};

export default function DocsPage() {
  return (
    <main className="flex-1 px-6 py-16">
      <article className="max-w-3xl mx-auto prose dark:prose-invert">
        <h1 className="text-3xl font-semibold tracking-tight">WACTL docs</h1>
        <p className="mt-4 text-zinc-600 dark:text-zinc-400">
          WACTL is a WhatsApp-first automation bot. You send a slash command in
          a DM; the bot replies with the processed result. Outgoing replies
          never go through the public webhook — they&apos;re pushed directly from
          the worker to the WhatsApp Cloud API.
        </p>

        <h2 className="mt-12 text-xl font-semibold tracking-tight">
          Getting started
        </h2>
        <ol className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
          <li>
            1. Open{" "}
            <a href={WA_ME_LINK} className="underline">
              the WhatsApp link
            </a>{" "}
            on your phone.
          </li>
          <li>2. Send any message to start the conversation.</li>
          <li>
            3. Type a slash command. For commands that need a file (e.g.{" "}
            <code>/pdf-docx</code>), attach the file in the same message.
          </li>
          <li>
            4. Wait a few seconds — sync commands reply inline, async ones
            (PDF→DOCX, audio) may take up to a minute on the worker.
          </li>
        </ol>

        <h2 className="mt-12 text-xl font-semibold tracking-tight">
          Command reference
        </h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {COMMANDS.map((cmd) => (
            <div
              key={cmd.name}
              className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-4"
            >
              <code className="text-sm font-mono text-emerald-700 dark:text-emerald-400">
                {cmd.name}
              </code>
              <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
                {cmd.description}
              </p>
              <p className="mt-2 text-xs font-mono text-zinc-500">
                {cmd.example}
              </p>
            </div>
          ))}
        </div>

        <h2 className="mt-12 text-xl font-semibold tracking-tight">
          Architecture
        </h2>
        <ul className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300 list-disc pl-5">
          <li>
            <strong>Webhook</strong> — AWS Lambda, ~50ms cold start. Validates
            the HMAC <code>X-Hub-Signature-256</code> header.
          </li>
          <li>
            <strong>Dedup</strong> — DynamoDB single-table, keyed on the
            Meta <code>wamid</code>, with a 7-day TTL matching Meta&apos;s retry
            window.
          </li>
          <li>
            <strong>Sync queue</strong> — fast commands (image resize,
            summary) run inline in Lambda. Budget: 10s.
          </li>
          <li>
            <strong>Async queue</strong> — heavy commands (PDF→DOCX, audio)
            are enqueued to SQS; an EC2 worker drains the queue.
          </li>
          <li>
            <strong>Storage</strong> — S3 media bucket with 24h lifecycle.
            Downloads are immediate (Meta&apos;s media URLs expire in 5 min).
          </li>
        </ul>

        <h2 className="mt-12 text-xl font-semibold tracking-tight">
          Limits &amp; quotas
        </h2>
        <ul className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300 list-disc pl-5">
          <li>Lambda timeout: 60s (sync commands must finish in this window).</li>
          <li>Worker visibility timeout: 15 min (jobs re-deliver if longer).</li>
          <li>WhatsApp media limit: 25 MB per inbound attachment.</li>
          <li>Audiobook generation caps at ~50 pages to stay under budget.</li>
        </ul>

        <p className="mt-12 text-sm text-zinc-500">
          Source on{" "}
          <a
            href="https://github.com/sathya-narayanan/wactl"
            className="underline"
          >
            GitHub
          </a>
          .
        </p>
      </article>
    </main>
  );
}