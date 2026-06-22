# Frontend Design System — Russel.AI

Dark "enterprise SaaS" theme. Every component must follow these rules.
Token source: `frontend/src/css/tokens.css`. Always use `var(--token)` — never hardcode hex values.

---

## Color System

### Backgrounds
| Role | Token | Value |
|---|---|---|
| Page background | `--color-bg` | `#0d0d0d` |
| Surface (cards, panels) | `--color-surface` | `#141414` |
| Raised surface (inputs, badges) | `--color-surface-raised` | `#1c1c1c` |

### Borders
| Token | Value |
|---|---|
| `--color-border` | `#2a2a2a` |

### Accent / Brand
| Role | Token | Value |
|---|---|---|
| Primary (amber) | `--color-primary` | `#f5a623` |
| Primary hover | `--color-primary-hover` | `#e6951a` |
| Secondary (navy) | `--color-secondary` | `#1a3a6b` |
| Info text (blue) | `--color-info-text` | `#7aabff` |

Amber (`#f5a623`) is the **only** warm accent. Use it for: one CTA per section, active states, focus rings, labels, icons. Never use it as a background fill beyond subtle overlays.

### Text
| Role | Token | Value |
|---|---|---|
| Primary (near-white) | `--color-text-primary` | `#f0f0f0` |
| Secondary (muted grey) | `--color-text-secondary` | `#9a9a9a` |
| Muted (disabled/placeholder) | `--color-text-muted` | `#555555` |

### Semantic (hardcoded, no token)
| Role | Value | Usage |
|---|---|---|
| Error / danger red | `#e05252` / `#e05c5c` | Error text, danger buttons |
| Success green | `#4caf72` | Online status dot |
| Score green | `#6fcf97` | Salary meta, positive scores |

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

`--space-5` is **not defined** — do not use it.

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
| Small meta | 10–12px | 600–700 | Often amber or muted |
| Button | 14px | 600 | `line-height: 1` |
| Input | 14px | 400 | — |

Heading letter-spacing is consistently `-0.02em`. All-caps labels consistently use `letter-spacing: 0.08em` or higher.

---

## Border Radius

| Token | Value | Used for |
|---|---|---|
| `--radius-sm` | 8px | Inputs, buttons, small cards |
| `--radius-lg` | 12px | Cards, modals, panels |
| `--radius-pill` | 9999px | Tags, badges, pills, clear buttons |
| `--radius-full` | 50% | Avatars, circular bubbles |

---

## Shadows & Glow

| Token | Value | Used for |
|---|---|---|
| `--shadow-card` | `0 4px 24px rgba(0,0,0,0.4)` | Job cards, content cards |
| `--shadow-modal` | `0 4px 24px rgba(0,0,0,0.5)` | Modals, dropdowns |
| `--shadow-glow-amber` | `0 0 20px rgba(245,166,35,0.2)` | Primary button hover, active elements |
| `--shadow-glow-navy` | `0 0 20px rgba(26,58,107,0.3)` | Navy-accented hover states |
| `--shadow-focus-ring` | `0 0 0 3px rgba(245,166,35,0.15)` | Input/select focus state |

---

## Component Styles

### Page Layout
Every page must be `height: 100vh; overflow: hidden` — no page-level scroll ever.
Long content goes inside an inner scroll container (`overflow-y: auto`).

```css
.page {
  height: 100vh;
  overflow: hidden;
  background-color: var(--color-bg);
  background-image: url('...');   /* each page has its own bg image */
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-8) var(--space-6) 0;
}
```

Inner scroll area pattern (used in Jobs, RecruiterDashboard, InterviewStages):
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
  transition: border-color 0.2s ease, transform 0.15s ease;
}
.card:hover {
  border-color: rgba(245, 166, 35, 0.4);    /* amber glow on hover */
  transform: translateY(-2px);
}
```

Job cards specifically:
- `min-height: 340px` desktop / `320px` tablet / `auto` mobile
- `display: flex; flex-direction: column; justify-content: space-between` — button always at bottom
- `box-sizing: border-box`

### Buttons

Three variants, all `border-radius: var(--radius-sm)` (8px), `padding: 12px 24px`, `font-size: 14px`, `font-weight: 600`:

| Variant | Normal | Hover |
|---|---|---|
| **primary** | amber bg (`--color-primary`), dark text (`--color-bg`) | `--color-primary-hover` + amber glow shadow |
| **secondary** | transparent bg, `--color-border` border, primary text | amber border + amber text |
| **ghost** | transparent bg + border, secondary text | primary text |

All transitions: `background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease`

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

Selects get a custom SVG chevron (grey `#9a9a9a`), `padding-right: 36px`, `appearance: none`.
Placeholders use `--color-text-muted`.

### Tags / Badges (Pills)
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

Variants:
- **active** — `rgba(245,166,35,0.15)` bg + amber text + `rgba(245,166,35,0.4)` border
- **info** — `rgba(26,58,107,0.4)` bg + `--color-info-text` text + navy border

### Modal
```css
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-6);
  z-index: 100;
}
.modal {
  width: 100%;
  max-width: 820px;
  max-height: calc(100vh - var(--space-6) * 2);
  background-color: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-modal);
  padding: var(--space-8);
  box-sizing: border-box;
  display: flex; flex-direction: column; overflow: hidden;
}
```

Inner scroll for long modal content: `flex: 1; min-height: 0; overflow-y: auto`.

### Fixed Utility Elements

**BackButton** — top-left of pages that aren't Home:
```css
position: fixed; top: var(--space-6); left: var(--space-6); z-index: 10;
background-color: var(--color-bg);
border: 1px solid var(--color-border);
border-radius: var(--radius-sm);
padding: var(--space-2) var(--space-3);
font-size: 13px; font-weight: 600;
/* hover: amber border + amber text */
```

**UserMenu** — top-right on every page (rendered in App.tsx outside AnimatePresence):
```css
position: fixed; top: var(--space-6); right: var(--space-6); z-index: 200;
```
Trigger: 38px circle. Amber border + glow when signed in. Status dot: 9px circle, green `#4caf72` online / `--color-text-muted` offline.

**Z-index ladder:**
| Layer | Value |
|---|---|
| BackButton | 10 |
| Modal backdrop | 100 |
| UserMenu | 200 |

---

## Layout Patterns

### Jobs Grid (4-column, responsive)
```css
display: grid;
grid-template-columns: repeat(4, 1fr);
gap: 20px;
align-items: stretch;    /* equal height rows */
max-width: 1400px;
```

| Breakpoint | Columns | Gap | Page padding |
|---|---|---|---|
| > 1199px | 4 | 20px | 24px |
| 900–1199px | 3 | 16px | 16px |
| 600–899px | 2 | 16px | 16px |
| < 600px | 1 | 12px | 12px |

### Filter Panel
`max-width: 1400px` — matches the jobs grid. `grid-template-columns: repeat(4, 1fr)` for filter inputs, collapses to 2 at 899px and 1 at 599px.

### Two-column Dialog (JobApplyDialog)
`display: flex; gap: var(--space-8)`. Left column `flex: 1.4`, right column `flex: 1`. Each column is an independent scroll container (`min-height: 0; overflow-y: auto`).

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

---

## Animations & Transitions

### Page Transitions
Framer Motion `AnimatePresence mode="wait"` wraps all routes in `App.tsx`.
`PageTransition` component: `opacity: 0 → 1` over `0.35s easeInOut`.

### Hover Transitions
Standard timing for interactive elements: `0.2s ease` on color/border/bg, `0.15s ease` on transform.
Card lift: `transform: translateY(-2px)`.

### Dropdown (UserMenu)
CSS-only, no JS animation library:
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
box-shadow: var(--shadow-focus-ring);   /* 0 0 0 3px rgba(245,166,35,0.15) */
```

### Loading Spinner
```css
border: 4px solid var(--color-border);
border-top-color: var(--color-primary);
border-radius: 50%;
animation: spin 0.8s linear infinite;
```

### Interview Room Animations
- **Bot float**: `translateY(0 → -18px)` over `3.2s ease-in-out infinite`
- **Stage bubble pulse**: `scale(1 → 1.15)` + `opacity(1 → 0.6)` over `1.4s ease-in-out infinite`
- **Timer ring**: `stroke-dashoffset` transition `1s linear`
- **Chat bubble in**: `opacity 0→1 + translateY(8px→0)` over `0.22s ease`
- **Timer urgent blink**: `opacity 1→0` step-end `1s infinite`
- **Warning popup**: multi-keyframe `opacity + translateY` over `6s ease forwards`

---

## Naming Conventions

- One `.css` file per component, co-located in `src/css/`, imported into matching `.tsx`.
- Class names follow BEM-like kebab-case: `component-element--modifier`.
- Page root class: `page-name-page` (e.g. `.jobs-page`, `.auth-page`, `.ir-page`).
- Scroll container inside page: `page-name-scroll-area` or `page-name-body`.
- All-caps label spans: `*-label` class, `font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em`.

---

## What Never to Do

- No white or light backgrounds — everything is `#0d0d0d` / `#141414` / `#1c1c1c`.
- No `min-height: 100vh` on page roots — always `height: 100vh; overflow: hidden`.
- No page-level scroll — all scrolling is in explicit inner containers with `min-height: 0`.
- No `--space-5` — it is not defined in tokens.
- No hardcoded hex values — use `var(--token)` for everything in the token set.
- No amber as a large fill — it is accent only (borders, text, icons, subtle overlays).
- No Tailwind, CSS-in-JS, or global utility classes.
