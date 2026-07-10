export const metadata = {
  title: "Terms — WACTL",
  description: "Terms of service for the WACTL WhatsApp bot.",
};

export default function TermsPage() {
  return (
    <main className="flex-1 px-6 py-16">
      <article className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-semibold tracking-tight">
          Terms of service
        </h1>
        <p className="mt-4 text-sm text-zinc-500">Last updated 2026-07-10.</p>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          Use at your own risk
        </h2>
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-300">
          WACTL is provided as-is, with no warranty of any kind. You are
          responsible for the files you send and the way you use the bot. We
          may rate-limit or ban abusive callers without notice.
        </p>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          No commercial use
        </h2>
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-300">
          WACTL is a personal-tooling platform. Reselling the service,
          scraping its outputs, or using it to process third-party data
          without consent is not permitted.
        </p>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          Acceptable content
        </h2>
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-300">
          You agree not to send files that are illegal in your jurisdiction,
          that infringe on others' intellectual property, or that contain
          malware. We may log and report such attempts.
        </p>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          Service changes
        </h2>
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-300">
          We may add, remove, or change commands at any time. We may
          deprecate the bot entirely with 30 days notice (posted here and on
          the GitHub repo).
        </p>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          Limitation of liability
        </h2>
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-300">
          To the maximum extent permitted by law, the operators of WACTL are
          not liable for any indirect, incidental, or consequential damages
          arising from use of the service.
        </p>

        <h2 className="mt-10 text-xl font-semibold tracking-tight">
          Governing law
        </h2>
        <p className="mt-4 text-sm text-zinc-700 dark:text-zinc-300">
          These terms are governed by the laws of the State of California,
          USA.
        </p>

        <p className="mt-12 text-sm text-zinc-500">
          Questions? Email <code>hello@wactl.example</code>.
        </p>
      </article>
    </main>
  );
}