# Russel-AI Frontend Design System

This is the single source of truth for visual design across the frontend.
Apply it to **every** component — buttons, navbar, cards, inputs, modals,
badges, tables, layouts, everything. Do not introduce ad-hoc colors, radii,
spacing, or shadows outside of this system.

CSS custom properties for every token below are defined in
[`src/css/tokens.css`](../src/css/tokens.css) and loaded globally via
`src/css/index.css`. Always reference `var(--token-name)` in component CSS
rather than hardcoding hex values.

## Colors

| Token | Variable | Value | Usage |
|---|---|---|---|
| Background | `--color-bg` | `#0d0d0d` | Main page background (near black) |
| Surface | `--color-surface` | `#141414` | Cards, modals, sidebars |
| Surface raised | `--color-surface-raised` | `#1c1c1c` | Hover states, dropdowns, input backgrounds |
| Border | `--color-border` | `#2a2a2a` | Subtle borders, dividers |
| Primary accent | `--color-primary` | `#F5A623` | CTAs, highlights, active states (amber/orange) |
| Primary hover | `--color-primary-hover` | `#e6951a` | Hover state for primary accent |
| Secondary accent | `--color-secondary` | `#1a3a6b` | Secondary buttons, tags, info states (deep navy) |
| Info text | `--color-info-text` | `#7aabff` | Text on navy/info badges |
| Text primary | `--color-text-primary` | `#f0f0f0` | Headings, main content |
| Text secondary | `--color-text-secondary` | `#9a9a9a` | Subtext, placeholders, captions |
| Text muted | `--color-text-muted` | `#555555` | Disabled, inactive |

**Rule:** No white backgrounds anywhere. Amber is the only warm color and is
used sparingly — one CTA per section, active states, icons. Navy is for
secondary/informational elements. Everything else is grayscale dark.

## Typography

- Font: `Inter` or `system-ui` sans-serif (`var(--font-sans)`)
- Headings: font-weight 600–700, letter-spacing `-0.02em`
- Body: font-weight 400, line-height 1.6
- Labels / all-caps text: font-size 11–12px, letter-spacing `0.08em`, uppercase

## Spacing

8px base unit. Use multiples of 4 / 8 / 12 / 16 / 24 / 32 / 48, available as
`--space-1` through `--space-12` in `tokens.css`.

## Shape Language

- Inputs / buttons: `border-radius: 8px` (`--radius-sm`)
- Cards / modals: `border-radius: 12px` (`--radius-lg`)
- Pills / chips: `border-radius: 9999px` (`--radius-pill`)
- Avatars: `border-radius: 50%` (`--radius-full`)
- Decorative background accents: subtle circles / rounded rectangles in
  `#1a1a1a`, used sparingly behind hero/empty-state content

## Shadows / Glow

| Token | Variable | Usage |
|---|---|---|
| `0 4px 24px rgba(0,0,0,0.4)` | `--shadow-card` | Cards |
| `0 4px 24px rgba(0,0,0,0.5)` | `--shadow-modal` | Modals |
| `0 0 20px rgba(245,166,35,0.2)` | `--shadow-glow-amber` | Active/featured elements |
| `0 0 20px rgba(26,58,107,0.3)` | `--shadow-glow-navy` | Info/secondary elements |
| `0 0 0 3px rgba(245,166,35,0.15)` | `--shadow-focus-ring` | Input focus ring |

## Components

### Buttons

- **Primary**: bg `--color-primary`, text `--color-bg`, font-weight 600,
  `border-radius: 8px`, padding `10px 20px` (py-2.5 px-5).
  Hover: bg `--color-primary-hover`, add `--shadow-glow-amber`.
- **Secondary**: bg transparent, `1px solid var(--color-border)`,
  text `--color-text-primary`.
  Hover: border-color `--color-primary`, text `--color-primary`.
- **Ghost**: no border, no background, text `--color-text-secondary`.
  Hover: text `--color-text-primary`.

### Cards

- bg `--color-surface`, `1px solid var(--color-border)`,
  `border-radius: 12px`, padding `24px`, `box-shadow: var(--shadow-card)`.
- Hover: border-color `--color-primary` at ~40% opacity
  (e.g. `rgba(245,166,35,0.4)`).

### Inputs / Forms

- bg `--color-surface-raised`, `1px solid var(--color-border)`,
  `border-radius: 8px`, text `--color-text-primary`,
  placeholder `--color-text-muted`.
- Focus: border-color `--color-primary`, `outline: none`,
  `box-shadow: var(--shadow-focus-ring)`.

### Navbar

- bg `--color-bg` with `border-bottom: 1px solid var(--color-border)`.
- Logo/brand in `--color-primary`, nav links in `--color-text-secondary`.
- Active/hover nav link: `--color-text-primary` with an amber underline or
  dot indicator.
- CTA button: primary amber button.

### Badges / Tags

- **Default**: bg `--color-surface-raised`, text `--color-text-secondary`,
  border `1px solid var(--color-border)`.
- **Active**: bg `rgba(245,166,35,0.15)`, text `--color-primary`,
  border `1px solid rgba(245,166,35,0.4)`.
- **Info**: bg `rgba(26,58,107,0.4)`, text `--color-info-text`,
  border `1px solid rgba(26,58,107,0.4)`.

## Overall Feel

Clean, minimal, dark enterprise SaaS. No white backgrounds. Amber used
sparingly for emphasis. Navy for secondary/informational elements.
Everything else grayscale dark.
