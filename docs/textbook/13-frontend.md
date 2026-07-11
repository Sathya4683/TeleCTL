# 13 — The Frontend (Next.js Marketing Site)

WACTL is a backend system. It doesn't *have* a frontend in the traditional sense — there's no login page, no dashboard, no user settings. The only UI is the marketing site at `wactl.example.com`, which is a single-page app that tells visitors what the system does and how to start using it.

This chapter walks through the Next.js site, the design choices, and the deployment.

## 13.1 — What's in `web/`

```
web/
├── app/
│   ├── layout.tsx             # root layout (metadata, theme)
│   ├── page.tsx               # landing page
│   ├── docs/page.tsx          # command reference
│   ├── privacy/page.tsx       # privacy notice
│   └── terms/page.tsx         # terms of service
├── components/
│   └── qr-code.tsx            # decorative SVG (NOT a real QR)
├── lib/
│   └── site.ts                # site-wide constants + the COMMANDS list
├── public/                    # static assets
├── package.json               # Node deps
├── package-lock.json
├── tsconfig.json
├── next.config.ts
├── next-env.d.ts
├── postcss.config.mjs
├── eslint.config.mjs
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
└── README.md
```

Four pages, one component, one constants file. That's the entire site. It's intentionally small.

## 13.2 — The stack

```json
{
  "dependencies": {
    "next": "16.2.10",
    "react": "19.2.4",
    "react-dom": "19.2.4"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "tailwindcss": "^4",
    "typescript": "^5",
    "eslint": "^9",
    "eslint-config-next": "16.2.10"
  }
}
```

- **[Next.js 16](https://nextjs.org/)** — the framework. App Router (the modern file-system-based routing).
- **[React 19](https://react.dev/)** — the UI library.
- **[Tailwind CSS v4](https://tailwindcss.com/)** — utility classes for styling.
- **[TypeScript 5](https://www.typescriptlang.org/)** — type safety.
- **[ESLint 9](https://eslint.org/)** with `eslint-config-next` — Next.js's recommended lint rules.

The site is **statically generated** (no dynamic routes, no API routes, no database). Next.js can pre-render every page at build time. The output is plain HTML + JS, served from a CDN.

The version of Next.js (16) is the modern one. The codebase has an `AGENTS.md` warning that the file structure may differ from training data — Next 16 introduced some changes from Next 13/14. The structure used (`app/` directory, React Server Components by default, `layout.tsx` and `page.tsx` files) is the Next 16 App Router convention.

## 13.3 — The landing page

`app/page.tsx` is the main page. Three sections:

1. **Hero.** A headline, a subhead, a CTA button ("Open in WhatsApp"), and a QR code.
2. **Commands.** A grid of cards, one per slash command.
3. **How it works.** A 4-step numbered list explaining the architecture.

The styling is Tailwind utility classes throughout. No external CSS files, no CSS-in-JS, no component library. The design is "clean, dark-mode-aware, lots of whitespace."

```tsx
<section className="flex flex-1 items-center justify-center px-6 py-24 bg-linear-to-b from-zinc-50 to-white dark:from-zinc-950 dark:to-black">
  <div className="max-w-3xl w-full grid sm:grid-cols-[1fr_auto] gap-12 items-center">
    ...
  </div>
</section>
```

The `dark:` prefix is Tailwind's dark-mode convention; combined with the `dark` class on the `<html>` element (set by the layout), it gives us free dark-mode support.

The `bg-linear-to-b` is Tailwind v4's gradient syntax (it replaced `bg-gradient-to-b` in v3).

## 13.4 — The COMMANDS list

The single source of truth for "what commands exist" lives in `web/lib/site.ts`:

```ts
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
  ...
];
```

This is **duplicated** with the Python side (`src/wactl/commands/*.py`). Each side has its own copy because the languages are different; the right answer is a single source of truth that generates both, but for 9 commands the duplication is manageable. A future improvement would be to generate the TS list from the Python registry (e.g. a script that reads `__init__.py` and outputs `site.ts`).

The `WA_ME_LINK` and `WA_ME_DISPLAY_NUMBER` are also in `site.ts`:

```ts
export const WA_ME_LINK = "https://wa.me/14155551234?text=%2Fhelp";
export const WA_ME_DISPLAY_NUMBER = "+1 (415) 555-1234";
```

The `wa.me/<number>?text=<urlencoded>` URL is Meta's "click to chat" link. Visiting it opens a WhatsApp chat with the number, pre-filled with the `text` parameter. The user just hits Send. (The numbers are placeholders — replace with the real business number for your deploy.)

## 13.5 — The QR code component

`components/qr-code.tsx` is a small SVG generator. Despite the name, it doesn't generate a *real* QR code (which would require a Reed-Solomon error-correction implementation). It draws a decorative pattern that looks QR-ish:

```tsx
export function QRCode({ data, size = 192 }: { data: string; size?: number }) {
  // Pseudo-random pattern based on the data string
  const cells = generateCells(data);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${cells.length} ${cells.length}`}>
      {cells.flatMap((row, y) =>
        row.map((on, x) =>
          on ? <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="currentColor" /> : null
        )
      )}
    </svg>
  );
}
```

The point isn't to be a real QR code (visitors can scan the link from the text below it or use the WhatsApp button). It's a visual element that suggests "scan me" without the implementation complexity.

If you need a real QR code, install `qrcode.react` and replace the component.

## 13.6 — The layout

`app/layout.tsx` is the root layout. It wraps every page:

```tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased min-h-screen flex flex-col bg-white text-zinc-950 dark:bg-black dark:text-zinc-50">
        {children}
      </body>
    </html>
  );
}
```

`<html lang="en">` is the standard accessibility flag. `suppressHydrationWarning` is a Next.js-specific flag to silence the warning that comes from dark-mode detection (the server renders with one class, the client may flip it on hydration).

The `body` gets the base colors and the dark-mode class. The `min-h-screen flex flex-col` makes the body fill the viewport and the footer stick to the bottom.

## 13.7 — The other pages

`app/docs/page.tsx` is a longer-form command reference — it lists every command with a longer description and an example. Useful as a `/help` alternative for users who want to read the docs before trying.

`app/privacy/page.tsx` and `app/terms/page.tsx` are short legal pages. They're required because the WhatsApp bot processes user data and outbound messages; Meta's terms of service require a privacy policy link and a terms link on any site that uses the WhatsApp Business API. The pages are minimal (no tracking, no third parties, no analytics) but they're there.

## 13.8 — Tailwind v4 setup

Tailwind v4 is configured via `postcss.config.mjs`:

```js
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```

And there's a CSS file (in `app/globals.css`, not shown but standard) that imports Tailwind:

```css
@import "tailwindcss";
```

That's it. No `tailwind.config.js` — Tailwind v4 uses CSS-first config. The dark mode is set by adding `dark` to a parent class.

## 13.9 — Running locally

```bash
cd web
npm install        # install deps (or pnpm install, or bun install)
npm run dev        # http://localhost:3000
```

The dev server has hot reload. The production build is `npm run build && npm run start`.

## 13.10 — Deployment: Vercel

The site is deployed to [Vercel](https://vercel.com/) (the company behind Next.js). Vercel has first-class Next.js support: push to Git, Vercel builds and deploys.

The CI workflow is `.github/workflows/deploy-frontend.yaml`:

```yaml
name: Deploy Frontend
on:
  push:
    branches: [main]
    paths: ['web/**']
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - working-directory: web
        run: npm ci
      - working-directory: web
        run: npm run build
      - uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          working-directory: web
          vercel-args: '--prod'
```

The workflow:

1. Triggers on push to `main` when files under `web/` change.
2. Installs deps with `npm ci` (clean install from lockfile).
3. Runs `npm run build` to produce the static output.
4. Uses the `vercel-action` to deploy.

The secrets (`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`) are stored in GitHub repo settings. Vercel issues the token when you create a project.

### Why Vercel and not S3+CloudFront?

Three reasons:

1. **Zero-config Next.js.** Vercel is made by the Next.js team. Image optimization, edge functions, ISR, etc. all work out of the box.
2. **Preview deploys on PR.** Every PR gets a unique URL; you can review the change visually before merging.
3. **Free tier.** 100 GB bandwidth/month, unlimited static sites. For a marketing page with a few hundred visitors, it's free.

The cost of Vercel: vendor lock-in. If you need to migrate, you'd need to host the static output somewhere else (S3+CloudFront works; just not with Vercel's image-optimization layer).

## 13.11 — Custom domain

The site is on a Vercel-provided subdomain by default (`wactl-xxx.vercel.app`). For a real deploy, you'd add a custom domain in Vercel settings and update the `WA_ME_LINK` in `site.ts` to point to the new URL.

The Vercel DNS setup is automatic; you just add an `A` record (or `CNAME` for subdomains) at your registrar. SSL is automatic.

## 13.12 — What we don't do

- **No analytics.** No Google Analytics, no Plausible, no Vercel Analytics. The site is a marketing page; the user activity is the WhatsApp conversation, not the site visit.
- **No cookies.** The site doesn't set any cookies. No consent banner needed.
- **No forms.** No newsletter signup, no contact form. The only call-to-action is the WhatsApp link.
- **No CMS.** The content is in the TS files. To update, you edit the file and push. No Sanity, no Contentful.
- **No i18n.** English only. WhatsApp itself is multi-language; the bot's user-facing strings (hint messages) are in English. Future: i18n via `next-intl` or similar.

The principle: **the site is a flyer, not an app.** It exists to tell people the system exists and to give them a way to start using it. Everything else is overhead.

## Next

→ [`14-local-development.md`](14-local-development.md) — running the project on your laptop: uv, environment variables, tests, building the worker image.
