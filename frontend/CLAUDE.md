# Frontend Guidelines

## Design System

This frontend uses a single dark "enterprise SaaS" design system. Apply it
to **every** component you create or edit — buttons, navbar, cards, inputs,
modals, badges, tables, layouts, everything.

Full spec: [`.claude/design-system.md`](.claude/design-system.md)
Tokens (CSS custom properties): [`src/css/tokens.css`](src/css/tokens.css)

Quick reference:

- Background `#0d0d0d`, surfaces `#141414` / `#1c1c1c`, borders `#2a2a2a`.
- Amber `#F5A623` is the *only* warm/accent color — use it sparingly (one
  CTA per section, active states, focus rings, icons).
- Navy `#1a3a6b` (text `#7aabff`) for secondary/info elements.
- Text: primary `#f0f0f0`, secondary `#9a9a9a`, muted `#555555`.
- No white backgrounds anywhere.
- Radius: 8px inputs/buttons, 12px cards, 9999px pills, 50% avatars.
- Spacing: 8px base unit (multiples of 4/8/12/16/24/32/48).
- Always use `var(--token-name)` from `tokens.css` instead of hardcoded
  hex values.

## Stack notes

- React + TypeScript + Vite, `react-router-dom` for routing.
- Plain CSS per component (no Tailwind/CSS-in-JS) — one `.css` file per
  component under `src/css/`, imported into the matching `.tsx`.
