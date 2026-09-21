# cursor_2027

A minimal [Vite](https://vite.dev) + [React](https://react.dev) + TypeScript starter used to
bootstrap and verify the Cloud Agent development environment. It renders a small interactive
task list so the app can be exercised end to end.

## Requirements

- Node.js 20+ (the Cloud Agent image ships Node 22)

## Getting started

```bash
npm ci        # install dependencies from the lockfile (use `npm install` if there is no lockfile yet)
npm run dev   # start the Vite dev server on http://localhost:5173
```

## Scripts

| Command          | Description                                      |
| ---------------- | ------------------------------------------------ |
| `npm run dev`    | Start the Vite dev server (host 0.0.0.0:5173).   |
| `npm run build`  | Type-check and build the production bundle.      |
| `npm run preview`| Preview the production build (host 0.0.0.0:4173).|
| `npm run lint`   | Lint the codebase with ESLint.                   |
| `npm test`       | Run the Vitest unit tests once.                  |

## Cloud Agent environment

The `.cursor/environment.json` file configures the Cloud Agent environment:

- `install` runs `npm ci` (falling back to `npm install` when no lockfile is present).
- A `dev` terminal runs the Vite dev server so the running app is always visible.
