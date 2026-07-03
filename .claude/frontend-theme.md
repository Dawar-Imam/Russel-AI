# Frontend Design System — Russel.AI

Dark "enterprise SaaS" theme (with a light theme variant). Every component must follow these rules.
Token source: `frontend/src/css/tokens.css`. Always use `var(--token)` — never hardcode hex values.

---

## Color System

### Backgrounds
| Role | Token | Dark | Light |
|---|---|---|---|
| Page background | `--color-bg` | `#0d0d0d` | `#f4f7fc` |
| Surface (cards, panels) | `--color-surface` | `#141414` | `#ffffff` |
| Raised surface (inputs, badges) | `--color-surface-raised` | `#1c1c1c` | `#eaf0f9` |

### Borders
| Token | Dark | Light |
|---|---|---|
| `--color-border` | `#2a2a2a` | `#d0dbe9` |

### Accent / Brand
| Role | Token | Dark | Light |
|---|---|---|---|
| Primary | `--color-primary` | `#f5a623` (amber) | `#1a73e8` (blue) |
| Primary hover | `--color-primary-hover` | `#e6951a` | `#1557b0` |
| Primary dark | `--color-primary-dark` | `#b5651d` | `#185abc` |
| Secondary | `--color-secondary` | `#1a3a6b` (navy) | `#dbeafe` |
| Info text | `--color-info-text` | `#7aabff` | `#1e40af` |
| Alert / danger | `--color-alert` | `#e05252` | `#d93025` |

In dark mode, amber is the **only** warm accent — one CTA per section, active states, focus rings, labels, icons, never a large background fill. Light mode swaps the whole accent to blue; the same usage rules apply to whichever `--color-primary` resolves to.

### RGB variants (for `rgba(var(--x-rgb), alpha)`)
`--color-primary-rgb`, `--color-secondary-rgb`, `--color-alert-rgb`, `--color-border-rgb`, `--color-muted-rgb`, `--color-info-text-rgb` — always use these instead of hardcoding an rgba() triplet.

### Glass tokens
`--glass-rgb` and `--glass-highlight-rgb` drive translucent glass panels layered over background photos (sidebar, glass inputs). `--shadow-rgb` is the base for all shadow tokens so shadows correctly darken/lighten per theme.

### Text
| Role | Token | Dark | Light |
|---|---|---|---|
| Primary | `--color-text-primary` | `#f0f0f0` | `#1e293b` |
| Secondary | `--color-text-secondary` | `#9a9a9a` | `#64748b` |
| Muted (disabled/placeholder) | `--color-text-muted` | `#555555` | `#94a3b8` |

### Theming mechanism
Light theme is applied via `body.light-theme` overriding the same token names — components never branch on theme directly, they just consume tokens. A handful of components (e.g. `.app-topbar-signed-in`, `.app-topbar-theme-toggle`, `.app-topbar-avatar-btn`) add explicit `body.light-theme .x { background-color: var(--color-surface) }` overrides where a transparent/dark-only look needs a solid backing in light mode. Background images are swapped per theme (`../utils/dark/*.png` vs `../utils/white/*.png`) and light mode layers a `--bg-overlay` linear-gradient tint (`--bg-overlay-alpha: 0.05`) over photos so pages don't read too white.

---

## Spacing

Base unit: **8px**. All spacing is a multiple of 4 or 8.

| Token | Value |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-12` | 48px |

`--space-5`, `--space-7`, etc. are **not defined** — only the values above exist.

---

## Layout Tokens

| Token | Value | Used for |
|---|---|---|
| `--sidebar-width` | 363px | Desktop sidebar |
| `--sidebar-margin` | 8px | Gap between sidebar/edge and sidebar/content |
| `--topbar-height` | 64px | `.app-topbar` height inside the content column |
| `--navbar-height` | 74px | Legacy/standalone nav height (pages outside the app shell) |

---

## Typography

```css
--font-sans: 'Inter', system-ui, sans-serif;
```

### Scale patterns (not tokenised, use px directly)
| Element | Size | Weight | Notes |
|---|---|---|---|
| Page heading | 28px | 700 | `letter-spacing: -0.02em` |
| Card title | 20px | 700 | `letter-spacing: -0.02em` |
| Section heading | 18px | 700 | — |
| Body / description | 13–15px | 400–600 | `line-height: 1.5–1.6` |
| Label (uppercase) | 11px | 600–700 | `letter-spacing: 0.08–0.1em; text-transform: uppercase` |
| Small meta | 10–12px | 600–700 | Often accent-colored or muted |
| Button | 14px | 600 | `line-height: 1` |
| Input | 14px | 400 | — |
| Sidebar nav link | 15px | 500 | — |
| Sidebar logo | 19px | 700 | `letter-spacing: -0.02em` |

Heading letter-spacing is consistently `-0.02em`. All-caps labels consistently use `letter-spacing: 0.04–0.1em`.

---

## Border Radius

| Token | Value | Used for |
|---|---|---|
| `--radius-sm` | 8px | Inputs, buttons, small cards |
| `--radius-lg` | 12px | Cards, modals, panels |
| `--radius-pill` | 9999px | Tags, badges, pills, status chips |
| `--radius-full` | 50% | Avatars, circular buttons |

The sidebar itself uses a one-off `14px` radius (not tokenised) since it's a floating glass panel, not a standard card.

---

## Shadows & Glow

| Token | Value | Used for |
|---|---|---|
| `--shadow-card` | `0 4px 24px rgba(var(--shadow-rgb), 0.4)` | Job cards, application cards, content cards |
| `--shadow-modal` | `0 4px 24px rgba(var(--shadow-rgb), 0.5)` | Modals, dropdowns |
| `--shadow-glow-amber` | `0 0 20px rgba(var(--color-primary-rgb), 0.2)` | Primary button hover, avatar hover, active elements |
| `--shadow-glow-navy` | `0 0 20px rgba(var(--color-secondary-rgb), 0.3)` | Secondary-accented hover states |
| `--shadow-focus-ring` | `0 0 0 3px rgba(var(--color-primary-rgb), 0.15)` | Input/select focus state |

Shadow alpha values are theme-aware (lighter shadows in light mode) because they read off `--shadow-rgb`, which itself flips per theme.

---

## Component Styles

### App Shell (sidebar + topbar)

The whole authenticated app (everything except `/`, `/auth`, and a few standalone pages) renders inside `AppLayout`, which owns a fixed sidebar + a topbar/content column. `shouldShowAppLayout(pathname, isSignedIn)` in `AppLayout.tsx` decides whether a route gets the shell.

```css
.app-shell {
  height: 100vh;
  width: 100%;
  overflow: hidden;
  display: flex;
}

.app-sidebar {
  position: fixed;
  top: var(--sidebar-margin); left: var(--sidebar-margin); bottom: var(--sidebar-margin);
  width: var(--sidebar-width);
  z-index: 200;
  background: rgba(var(--glass-rgb), 0.55);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(var(--glass-highlight-rgb), 0.1);
  border-radius: 14px;
  padding: var(--space-4) var(--space-3);
}

.app-main {
  margin-left: calc(var(--sidebar-width) + var(--sidebar-margin) * 2);
  width: calc(100% - var(--sidebar-width) - var(--sidebar-margin) * 2);
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-topbar {
  flex-shrink: 0;
  height: var(--topbar-height);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-4);
  padding: 0 var(--space-6);
}

.app-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
```

Sidebar nav links use `.app-sidebar-link` / `.app-sidebar-link--active` (active = primary text + `rgba(primary, 0.1)` background). A theme toggle and a user avatar button live in the topbar; the avatar opens `.app-topbar-dropdown` (profile info, logout with an inline confirm step) using the same fade/scale pattern as the old UserMenu (see Animations below).

**Responsive:**
- `≤1023px` — sidebar shrinks to `220px`, content margin adjusts to match.
- `≤599px` — sidebar becomes a bottom-docked horizontal bar (`height: 56px`, `flex-direction: row`, logo/divider/spacer hidden), `.app-main` drops its left margin and fills the width above it.

### Page Layout (pages, standalone or inside the shell)

Every page root must still be non-scrolling at the top level: `height: 100vh` (or `flex: 1; min-height: 0` for pages inside `.app-content`) with `overflow: hidden`. Long content goes inside an inner scroll container (`overflow-y: auto`).

```css
.page {
  height: 100vh;           /* or flex: 1; min-height: 0 inside the app shell */
  overflow: hidden;
  background-color: var(--color-bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-8) var(--space-6) 0;
}
```

Background photos are applied one of two ways, both theme-routed via tokens (`--bg-image-1..4`, `--bg-home-page`, `--bg-interview-room`):
- A `::before` pseudo-element (`z-index: -1`, `background-size: cover`) for pages inside the app shell (Jobs, MyApplications, RecruiterDashboard, ApplicationProgress).
- Inline `background-image` on the page root for standalone pages (Auth, InterviewRoom, InterviewStages).

Inner scroll area pattern (used in Jobs, MyApplications, RecruiterDashboard, InterviewStages):
```css
.page-scroll-area {
  flex: 1;
  width: 100%;
  min-height: 0;          /* critical — allows flex child to shrink */
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-bottom: var(--space-8);
}
```

### Cards
```css
.card {
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);           /* 12px */
  padding: var(--space-6);                   /* 24px */
  box-shadow: var(--shadow-card);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);                       /* 16px */
  transition: border-color 0.2s ease, transform 0.15s ease;
}
.card:hover {
  border-color: rgba(var(--color-primary-rgb), 0.4);
  transform: translateY(-2px);
}
```

Job cards (`.job-card`), application cards (`.app-card`), and recruiter dashboard job cards (`.rd-job-card`) all follow this exact pattern:
- `min-height: 340px`
- `display: flex; flex-direction: column; justify-content: space-between` — button always at bottom
- `.rd-job-card` additionally gets `box-shadow: var(--shadow-glow-amber)` layered onto the hover shadow

### Status badges / pills
Every domain has its own status-badge namespace, but they share one shape: `padding: 2–4px 10–12px`, `border-radius: var(--radius-pill)`, `font-size: 11–12px`, `font-weight: 600–700`, `border: 1px solid`.

| Namespace | Example classes | Pattern |
|---|---|---|
| Application cards | `.app-card-status--pending/pass/fail/hired/rejected/progress/scheduled` | pass/hired → primary text; fail/rejected → alert text; others → secondary/primary text, border always `--color-border` |
| Recruiter dashboard | `.rd-status-badge--[status]`, `.rd-badge`, `.rd-badge--salary` | salary badge uses primary text |
| Interview stages / ATS | `.ap-stage-badge--pending/in-progress/pass/fail`, `.ats-result-card--pass/fail` | pending/in-progress → `rgba(primary, 0.1)` bg + `rgba(primary, 0.3)` border; pass → primary; fail → `rgba(alert, 0.1)` bg + `rgba(alert, 0.3)` border |

### Buttons

Base `.btn`: `border-radius: var(--radius-sm)` (8px), `padding: 12px 24px`, `font-size: 14px`, `font-weight: 600`, `font-family: var(--font-sans)`.

| Variant | Normal | Hover |
|---|---|---|
| **primary** (`.btn-primary`) | primary bg, `--color-bg` text | `--color-primary-hover` bg + `--shadow-glow-amber` |
| **secondary** (`.btn-secondary`) | transparent bg, `--color-border` border, primary text | primary border + primary text |
| **ghost** (`.btn-ghost`) | transparent bg + border, secondary text | primary text |

All transitions: `background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease`.

Page-specific pill CTAs (e.g. `.rd-post-job-btn`, `.interview-stages-cta`, `.app-progress-cta`) reuse the same primary look but at `border-radius: var(--radius-pill)` with a `0 4px 20px rgba(primary, ...)` shadow and `translateY(-2px)` on hover.

### Inputs & Selects
```css
background-color: var(--color-surface-raised);
border: 1px solid var(--color-border);
border-radius: var(--radius-sm);
color: var(--color-text-primary);
padding: 10px 14px;
font-size: 14px;
transition: border-color 0.2s ease, box-shadow 0.2s ease;

/* focus */
border-color: var(--color-primary);
box-shadow: var(--shadow-focus-ring);
```

Native `<select>` gets a custom SVG chevron (`#9a9a9a`), `padding-right: 36px`, `appearance: none`. Placeholders use `--color-text-muted`.

`CustomSelect` (the app's own dropdown component, used in filters etc.) uses a "glass" variant instead of the raised surface:
```css
background: rgba(var(--glass-highlight-rgb), 0.06);
border: 1px solid rgba(var(--color-border-rgb), 0.7);
border-radius: var(--radius-sm);
padding: 9px 12px;
```
Its option list (`.cs-list`) is `position: absolute`, `z-index: 50`, `max-height: 220px`, gains a primary border when open; the chevron rotates `180deg` over `0.15s ease`; hovered/selected options get primary bg + `--color-bg` text. `FilterPanel` inputs/selects reuse this same glass pattern (`rgba(glass-highlight, 0.06)` bg, `rgba(border, 0.7)` border), including salary range inputs with an absolute-positioned `$` prefix (`padding-left: 22px`).

### Tags (generic, non-status)
```css
.tag {
  display: inline-flex;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 500;
  border: 1px solid var(--color-border);
  background-color: var(--color-surface-raised);
  color: var(--color-text-secondary);
}
```
Variants: `.tag-active` (`rgba(primary, 0.15)` bg + primary text + `rgba(primary, 0.4)` border), `.tag-info` (surface-raised bg + primary text color), `.tag-clickable` (hover → primary border/text).

### Modal
```css
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(var(--shadow-rgb), 0.6);
  backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  padding: 88px 24px 24px;   /* top padding clears the topbar */
  z-index: 100;
}
.modal {
  width: 100%;
  max-width: 860px;
  height: calc(100vh - 88px - 24px);
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-modal);
  padding: var(--space-8);
  box-sizing: border-box;
  display: flex; flex-direction: column; overflow: hidden;
}
```
Inner scroll for long modal content: `flex: 1; min-height: 0; overflow-y: auto`. When the app has a sidebar, the backdrop clamps its left edge to the sidebar boundary rather than covering it.

### User Menu (topbar dropdown)
Lives in `.app-topbar-user` / `.app-topbar-dropdown`, not a separate fixed component:
```css
.app-topbar-dropdown {
  position: absolute;
  top: calc(100% + 10px); right: 0;
  width: 210px;
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-modal);
  padding: var(--space-3);
  opacity: 0;
  transform: translateY(-8px) scale(0.97);
  pointer-events: none;
  transition: opacity 0.18s ease, transform 0.18s ease;
  z-index: 210;
}
.app-topbar-dropdown--open {
  opacity: 1;
  transform: translateY(0) scale(1);
  pointer-events: auto;
}
```
Contains a profile row (avatar initials + role label + email), a divider, and action buttons — logout uses `--color-alert` text and expands into an inline two-button confirm step (`.app-topbar-dd-logout-confirm-btn--danger`) rather than a separate modal.

### Fixed / Positioned Utility Elements

**BackButton** — top-left of standalone pages not inside the app shell:
```css
position: fixed; top: var(--space-6); left: var(--space-6); z-index: 10;
background-color: var(--color-bg);
border: 1px solid var(--color-border);
border-radius: var(--radius-sm);
padding: var(--space-2) var(--space-3);
font-size: 13px; font-weight: 600;
/* hover: primary border + primary text */
```
Pages that render their own back control instead (InterviewRoom's `.ir-back-float`, absolute top-left) don't use `BackButton`.

**Page floating CTAs** — bottom-right, used on InterviewStages/ApplicationProgress:
```css
position: fixed; bottom: 32px; right: 32px;
```

**Z-index ladder:**
| Layer | Value |
|---|---|
| BackButton | 10 |
| InterviewRoom back float | 5 |
| InterviewRoom bottom bar | 20 |
| Modal backdrop | 100 |
| Sidebar | 200 |
| Topbar user dropdown | 210 |

---

## Layout Patterns

### Card grid (Jobs, MyApplications, RecruiterDashboard — same pattern everywhere)
```css
display: grid;
grid-template-columns: repeat(3, 1fr);
gap: 20px;
align-items: stretch;    /* equal height rows */
```

| Breakpoint | Columns | Gap | Page padding |
|---|---|---|---|
| > 1199px | 3 | 20px | 24px |
| 900–1199px | 2 | 16px | 16px |
| 600–899px | 1 | 16px | 16px |
| < 600px | 1 | 12px | 12px |

Cards stay `width: 100%` of their grid track with no max-width cap — the grid's column count, not the card, controls sizing.

### Filter Panel
Flex-based, not grid: `.filter-panel` is a flex column (`gap: 12px`), with `.filter-panel-row` as a wrapping flex row (`gap: 16px`) and each `.filter-panel-field` at `flex: 1 1 160px` (`min-width: 140px`). At `≤1199px` fields grow to `flex: 1 1 200px`; at `≤599px` the row becomes a 2-column grid (`gap: 12px`).

### Two-column dialog (JobApplyDialog)
`display: flex; gap: 32px`. Left/main column `flex: 1.4`, right/side column `flex: 1` (`overflow-y: auto`). Collapses to `flex-direction: column` at `≤560px`.

### ApplicationProgress content row
`display: flex; gap: 28px`, `max-height: calc(100vh - topbar - ~260px)`. Left pane fixed at `flex: 0 0 300px` (scrollable), detail pane `flex: 1`, an optional rightmost test panel at `flex: 0 0 160px`. Collapses to `flex-direction: column` at `≤600px`.

### Interview Stages
Flex row, `flex-wrap`, `gap: 32px`, with a horizontal connector line (`::before`, `4px` tall, primary color) running behind 130×130px absolutely-positioned stage bubbles.

---

## Scrollbar Styling

Thin, consistent across all scroll containers:
```css
scrollbar-width: thin;
scrollbar-color: var(--color-border) transparent;

::-webkit-scrollbar { width: 4–5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 2–3px; }
::-webkit-scrollbar-thumb:hover { background: var(--color-text-muted); }
```
The Jobs scroll area instead hides the scrollbar entirely (`display: none`) and masks overflow with a gradient fade.

---

## Animations & Transitions

### Page Transitions
Framer Motion is used for exactly one thing: `PageTransition` wraps every routed page (`AnimatePresence mode="wait"` in `App.tsx`), fading `opacity: 0 → 1` over `duration: 0.35, ease: 'easeInOut'`. Everything else below is plain CSS — no other Framer Motion usage in the codebase.

### Hover Transitions
Standard timing for interactive elements: `0.2s ease` on color/border/background/box-shadow, `0.15s ease` on transform. Card lift: `transform: translateY(-2px)`.

### Dropdowns (topbar user menu, CustomSelect)
CSS-only:
```css
/* closed */
opacity: 0;
transform: translateY(-8px) scale(0.97);
pointer-events: none;
transition: opacity 0.18s ease, transform 0.18s ease;

/* open (class toggled by JS) */
opacity: 1;
transform: translateY(0) scale(1);
pointer-events: auto;
```

### Focus Ring
Applied via `box-shadow`, no outline:
```css
outline: none;
border-color: var(--color-primary);
box-shadow: var(--shadow-focus-ring);
```

### Loading Spinner
```css
border: 4px solid var(--color-border);
border-top-color: var(--color-primary);
border-radius: 50%;
animation: spin 0.8s linear infinite;
```
(`ir-spin` in InterviewRoom, `profile-spin` in UserProfile — same shape, page-scoped keyframe names.)

### Interview Room Animations
- **Bot float** (`ir-float`): `translateY(0 → -18px → 0)` over `3.2s ease-in-out infinite`
- **Timer urgent pulse** (`ir-timer-pulse`): `opacity 1 → 0 → 1` (55% off-point) over `1s ease-in-out infinite`
- **Chat bubble in** (`ir-bubble-in`): `opacity 0→1 + translateY(8px→0)` over `0.22s ease both`
- **Cursor blink** (`ir-blink`): `opacity 1→0` step-end, `0.7s infinite`
- **Warning popup** (`ir-warn-popup`): multi-keyframe `opacity + translateY(10px→0)` over `6s ease forwards`

### Other keyframe animations
- **Stage pulse** (`stage-pulse`, InterviewStages): `scale(1→1.15→1)` + `opacity(1→0.6→1)` over `1.4s ease-in-out infinite`
- **ATS pending glow** (`ats-pending-glow`): `box-shadow` pulses between `--shadow-glow-amber` and `0 0 28px rgba(primary, 0.45)` over `1.5s ease-in-out infinite`
- **Accordion panel open** (`ap-panel-in`, ApplicationProgress): `opacity 0→1 + translateY(-4px→0)` over `0.18s ease`

---

## Naming Conventions

- One `.css` file per component, co-located in `src/css/`, imported into matching `.tsx`.
- Class names follow BEM-like kebab-case with a page/component prefix: `prefix-element` or `prefix-element--modifier`.
- Page root class: `page-name-page` (e.g. `.jobs-page`, `.auth-page`, `.ir-page`, `.rd-page`, `.interview-stages-page`, `.app-progress-page`).
- Scroll container inside page: `page-name-scroll-area`.
- Domain prefixes in use: `ir-` (InterviewRoom), `rd-` (RecruiterDashboard), `ap-` (ApplicationProgress), `ats-` (ATS result UI inside InterviewStages), `cs-` (CustomSelect), `app-` (AppLayout shell/topbar/sidebar — distinct from `.app-card`, which belongs to ApplicationCard).
- State modifiers are always `--modifier` suffixes: `--active`, `--open`, `--pending`, `--pass`, `--fail`, `--urgent`, `--selected`, etc.
- All-caps label spans: `*-label` class, `font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em`.

---

## What Never to Do

- No hardcoded hex values — use `var(--token)` for everything in the token set, including `rgba()` triplets (use the `-rgb` tokens).
- No `min-height: 100vh` on page roots — always `height: 100vh; overflow: hidden` (or `flex: 1; min-height: 0` inside the app shell).
- No page-level scroll — all scrolling is in explicit inner containers with `min-height: 0`.
- No skipping the theme system — every color must resolve through a token so `body.light-theme` can override it; never branch styles on a theme class unless the token system genuinely can't express the difference (see the few explicit `body.light-theme .x` overrides in AppLayout.css for the rare exception).
- No amber (or whatever `--color-primary` resolves to) as a large fill — it is accent only (borders, text, icons, subtle overlays, one CTA per section).
- No Tailwind, CSS-in-JS, or global utility classes.
- No new Framer Motion usage outside `PageTransition` without discussing it first — the rest of the app is intentionally plain CSS.
