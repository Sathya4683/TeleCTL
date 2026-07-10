/**
 * Site-wide constants. Anything user-facing that's referenced from more
 * than one page lives here so we don't end up with hard-coded strings
 * scattered across the app.
 */
export const WA_ME_LINK = "https://wa.me/14155551234?text=%2Fhelp";

export const WA_ME_DISPLAY_NUMBER = "+1 (415) 555-1234";

export const REPO_URL = "https://github.com/sathya-narayanan/wactl";

export const COMMANDS: ReadonlyArray<{
  name: string;
  description: string;
  example: string;
}> = [
  {
    name: "/pdf-docx",
    description: "Convert an attached PDF to a DOCX, preserving layout.",
    example: "Send /pdf-docx with a PDF attached.",
  },
  {
    name: "/pdf-audio",
    description: "Read an attached PDF aloud as a single audio message.",
    example: "Send /pdf-audio with a PDF.",
  },
  {
    name: "/merge-pdf",
    description: "Combine two or more PDFs into one document.",
    example: "Send /merge-pdf followed by several PDFs.",
  },
  {
    name: "/split-pdf",
    description: "Split an attached PDF into one file per page.",
    example: "Send /split-pdf with a PDF.",
  },
  {
    name: "/image-resize",
    description: "Resize an attached image to given pixel dimensions.",
    example: "/image-resize 800x600 (with image attached)",
  },
  {
    name: "/image-compress",
    description: "Recompress an attached image to reduce file size.",
    example: "/image-compress quality=70 (with image)",
  },
  {
    name: "/web-summary",
    description: "Fetch a URL and reply with a concise summary.",
    example: "/web-summary https://example.com/article",
  },
  {
    name: "/github-pr",
    description: "Summarise a GitHub pull request's diff.",
    example: "/github-pr https://github.com/owner/repo/pull/123",
  },
  {
    name: "/translate",
    description: "Translate text or an attached document to a target language.",
    example: "/translate es: Hello, world!",
  },
];