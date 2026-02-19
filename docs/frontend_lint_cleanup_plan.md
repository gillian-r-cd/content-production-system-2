# Frontend Lint Cleanup Plan (Phased)

## Baseline (2026-02-19)

- Total issues: 322 (252 errors, 70 warnings)
- Files with issues: 33
- Top rules:
  - `@typescript-eslint/no-explicit-any`: 236
  - `@typescript-eslint/no-unused-vars`: 56
  - `react/no-unescaped-entities`: 14
  - `react-hooks/exhaustive-deps`: 13
- Top files:
  - `frontend/lib/api.ts`: 89
  - `frontend/components/eval-field-editors.tsx`: 44
  - `frontend/components/eval-phase-panel.tsx`: 37

## Principles

1. Fix correctness and runtime risks first, then style debt.
2. Prioritize active Eval V2 surfaces before broad cleanup.
3. Keep each batch independently verifiable with targeted lint commands.
4. Avoid broad suppressions; prefer real type narrowing and explicit interfaces.

## Batch Plan

### Batch 1 (In progress): Eval V2 critical path

- Scope:
  - `frontend/components/eval-phase-panel.tsx`
  - `frontend/components/eval-field-editors.tsx`
  - `frontend/components/layout/workspace-layout.tsx`
- Goal:
  - Resolve correctness-level lint failures.
  - Start reducing `no-explicit-any` in Eval V2 report/config paths.
- Validation:
  - `npm run lint:batch:eval`

### Batch 2: API typing foundation

- Scope:
  - `frontend/lib/api.ts` (Eval V2 related sections first)
- Goal:
  - Replace broad `any` responses with narrow interfaces for execution/task/report payloads.
  - Reduce repeated unsafe casts in consuming components.
- Validation:
  - `npm run lint:batch:eval`
  - `npx tsc --noEmit`

### Batch 3: Settings pages and shared components

- Scope:
  - `frontend/app/settings/page.tsx`
  - `frontend/components/settings/*`
  - `frontend/components/content-panel.tsx`
- Goal:
  - Resolve no-explicit-any + hook dependency warnings with memoized callbacks.
  - Fix unescaped entity violations.

### Batch 4: Global sweep and gating

- Scope:
  - Full frontend
- Goal:
  - Run full lint and keep issue count trending downward every PR.
  - Add CI gate for touched files (no new lint debt).
- Validation:
  - `npm run lint`



