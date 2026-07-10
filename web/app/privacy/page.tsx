export const metadata = {
  title: "Privacy — WACTL",
  description: "What WACTL stores about you, and for how long.",
};

export default function PrivacyPage() {
  return (
    <main className="flex-1 px-6 py-16">
      <article className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-semibold tracking-tight">
          Privacy notice
        </h1>
        <p className="mt-4 text-sm text-zinc-500">Last updated 2026-07-10.</p>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          What we collect
        </h2>
        <ul className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300 list-disc pl-5">
          <li>
            <strong>WhatsApp metadata</strong> — your phone number, message
            ID (<code>wamid</code>), and the Business number you DM'd.
          </li>
          <li>
            <strong>Media you send</strong> — PDFs, images, audio, video that
            you attach. Stored in an S3 bucket for the duration of processing
            (≤24 hours) and then auto-deleted.
          </li>
          <li>
            <strong>Command arguments</strong> — anything you type after the
            slash command (URLs, language codes, dimensions).
          </li>
          <li>
            <strong>Processed outputs</strong> — the file we send back to you
            (e.g. the converted DOCX). Held briefly in S3 for delivery.
          </li>
        </ul>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          How long we keep it
        </h2>
        <ul className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300 list-disc pl-5">
          <li>
            <strong>Dedup records</strong> — 7 days (matches Meta's retry
            window). Dropped automatically via DynamoDB TTL.
          </li>
          <li>
            <strong>Media files</strong> — 24 hours, then lifecycle-expired
            from S3.
          </li>
          <li>
            <strong>CloudWatch logs</strong> — 30 days. Logs are scrubbed of
            message bodies; only metadata + structured event names are kept.
          </li>
        </ul>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          What we do NOT do
        </h2>
        <ul className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300 list-disc pl-5">
          <li>We do not sell or share your data with third parties.</li>
          <li>We do not train models on your media.</li>
          <li>
            We do not log message bodies (only structural metadata).
          </li>
        </ul>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          Third-party services
        </h2>
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-300">
          Files sent through WACTL may be transmitted to one of these
          sub-processors, depending on the command:
        </p>
        <ul className="mt-4 space-y-2 text-sm text-zinc-700 dark:text-zinc-300 list-disc pl-5">
          <li>
            <strong>Google Gemini</strong> — for <code>/translate</code>,{" "}
            <code>/web-summary</code>, <code>/github-pr</code>, and audiobook
            TTS.
          </li>
          <li>
            <strong>GitHub REST API</strong> — for <code>/github-pr</code>.
          </li>
          <li>
            <strong>WhatsApp Cloud API (Meta)</strong> — for media download
            and message delivery.
          </li>
        </ul>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">Contact</h2>
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-300">
          Email <code>privacy@wactl.example</code> to request deletion of any
          data we hold about you. Requests are processed within 30 days.
        </p>
      </article>
    </main>
  );
}