# Open-GrokBot web

Next.js 16 App Router frontend for the persistent Bot roster and one-to-one conversation experience.

## Structure

- `app/page.tsx` is the server-rendered route boundary.
- `app/workspace.tsx` coordinates roster, conversation, SSE, and cancellation state.
- `app/components/` contains isolated interactive product components.
- `lib/api.ts` is the typed HTTP boundary; `lib/types.ts` contains transport types.
- `app/*.test.tsx` covers component behavior with Vitest and Testing Library.
- `e2e/` contains release-focused Playwright acceptance flows. The full release suite covers the –product suite when the deterministic Compose stack is running.

## Run and verify

```bash
npm ci
npm run dev
npm run typecheck
npm run lint
npm run test
npm run build
npm run test:e2e
```

Set `NEXT_PUBLIC_API_URL` when the API is not at `http://localhost:8000`.
