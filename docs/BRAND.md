# Protocōl Brand Tokens (v2 — Teal Scheme, Light + Dark)

**Status:** Adopted June 2026, supersedes the v1 gold-on-black identity.

## Why we changed

The v1 gold-on-black identity (`#FFB612` on `#0E0E10`) was a strong identity but
read as gaming-adjacent / dashboard-utility. The v2 teal identity reads as
editorial, clinical-credible, and suitable for consumer-facing (deck, PDFs,
marketing) and signed-in app surfaces alike.

**Two modes, one scheme.** Light mode is the canonical brand and the only mode
used by the deck and PDFs. Dark mode is a brightness-adjusted variant of the
same palette for the app — primary brightens, surfaces darken, semantic states
recover their saturated form.

## Canonical palette (light mode)

| Token            | Hex       | Role                                                                |
| ---------------- | --------- | ------------------------------------------------------------------- |
| `bg`             | `#F7F6F2` | App / page background. Warm cream, not pure white.                  |
| `surface`        | `#F9F8F5` | Card / panel fill. Slightly lighter than `bg` for subtle elevation. |
| `surface-strong` | `#EFEDE6` | Sidebar / sticky-bar fill.                                          |
| `border`         | `#D4D1CA` | Card / table border. 0.5pt in print, 1px in app.                    |
| `border-strong`  | `#B9B5AC` | Active / focus borders.                                             |
| `text`           | `#28251D` | Primary body text on light.                                         |
| `muted`          | `#7A7974` | Secondary body / metadata text.                                     |
| `faint`          | `#BAB9B4` | Disabled / tertiary text.                                           |
| `primary`        | `#01696F` | **Hydra Teal.** Accents, primary actions, big numbers.              |
| `primary-dark`   | `#0C4E54` | Hover state, Q4-style emphasis (deck slide 11).                     |
| `primary-mist`   | `#BCE2E7` | Secondary text on dark surfaces.                                    |
| `dark`           | `#0C2A2D` | Dark surface (cover slides, dark accent cards).                     |
| `dark-edge`      | `#1B474D` | Dividers on dark surfaces.                                          |

### Semantic states (kept distinct from accent)

| Token     | Hex       | Role                                  |
| --------- | --------- | ------------------------------------- |
| `success` | `#2E7D5B` | Optimal range, deltas trending right. |
| `warn`    | `#B5651D` | Monitor / borderline.                 |
| `danger`  | `#A8341E` | Out-of-range, high risk.              |
| `info`    | `#01696F` | Same as primary — informational.      |

State colors shifted from v1's saturated `#4CAF50 / #FF9800 / #F44336` to muted
earth-tones that sit better on a cream surface. The semantic meaning is preserved.

## Chart palette (extends primary)

| Token | Hex       | Role                                |
| ----- | --------- | ----------------------------------- |
| `c1`  | `#20808D` | Primary series.                     |
| `c2`  | `#A84B2F` | Rust — second series / contrast.    |
| `c3`  | `#1B474D` | Deep teal — third series.           |
| `c4`  | `#BCE2E7` | Mist — fill / area.                 |
| `c5`  | `#944454` | Mulberry — fourth / categorical.    |
| `c6`  | `#FFC553` | Amber — fifth / categorical accent. |

## Type system

| Role                  | Family                                  | Notes                                    |
| --------------------- | --------------------------------------- | ---------------------------------------- |
| Display (deck, PDFs)  | **Trebuchet MS**                        | System-safe across Mac/Windows.          |
| Body (deck, PDFs)     | **Calibri**                             | System-safe across Mac/Windows.          |
| App (Streamlit)       | System sans (Streamlit default)         | Don't override — system font is correct. |
| Numeric (KPI, tables) | `font-variant-numeric: tabular-nums`    | Always. Locks digit widths.              |

## Layout grammar

- **Surface motif:** rectangular cards (no rounded corners) on `surface` fill
  with `border` at 0.5pt (print) or 1px (app).
- **Eyebrows:** ALL-CAPS letter-spaced primary-teal labels (`charSpacing: 2`,
  ~10pt). Used in deck/PDF top-right, app section headers.
- **Page numbers:** `N / total` bottom-right, `muted` color, 9pt.
- **Accent rules:** thin `primary` rectangles, 0.04"–0.06" tall, used sparingly
  (cover slides, brand bar dividers).
- **No icons inside accent shapes.** Use icons in body content; keep accent
  shapes pure rectangles.

## Identity assets

- **Wordmark:** "Protocōl" with the ō macron, always. Never "Protocol".
- **Mark:** Chevron-shield SVG (three ascending chevrons in a heraldic shield),
  recolored from gold to `primary` teal. Source in
  `protocl/modules/theme.py::render_top_brand`.

## Dark-mode palette

The app supports a dark mode using the same teal scheme. Primary brightens to
maintain contrast on near-black surfaces; semantic states return to their
saturated v1 values because they need to compete with a dark background.

| Token            | Light       | Dark        | Role                                  |
| ---------------- | ----------- | ----------- | ------------------------------------- |
| `bg`             | `#F7F6F2`   | `#0C1E20`   | Page background.                      |
| `surface`        | `#F9F8F5`   | `#152A2D`   | Card / panel fill.                    |
| `surface-strong` | `#EFEDE6`   | `#0F2326`   | Sidebar / sticky-bar fill.            |
| `border`         | `#D4D1CA`   | `rgba(60,180,190,0.20)` | Card / table border.      |
| `border-strong`  | `#B9B5AC`   | `rgba(60,180,190,0.40)` | Focus / active borders.   |
| `text`           | `#28251D`   | `#E8E5DA`   | Primary text.                         |
| `muted`          | `#7A7974`   | `#A0A8A8`   | Secondary text / metadata.            |
| `faint`          | `#BAB9B4`   | `#6C7475`   | Disabled / tertiary text.             |
| `primary`        | `#01696F`   | `#3CB4BE`   | Accent / primary actions / big numbers. |
| `primary-soft`   | `rgba(1,105,111,0.08)` | `rgba(60,180,190,0.18)` | Soft-fill / hover state. |
| `success`        | `#2E7D5B`   | `#4CAF50`   | Optimal / trending right.             |
| `warn`           | `#B5651D`   | `#FF9800`   | Monitor / borderline.                 |
| `danger`         | `#A8341E`   | `#F44336`   | Out-of-range / high risk.             |

### Mode selection

- Default at session start: **light**.
- User toggles mode in the sidebar (Display group). Stored in `st.session_state["theme_mode"]`.
- The app sets a `data-theme="light|dark"` attribute on `<body>` and the CSS
  uses CSS custom properties keyed off that attribute. **All component CSS
  reads tokens via `var(--brand-*)` — no hard-coded hexes outside the token
  block in `modules/theme.py`.**

## Surface examples

| Surface              | bg / text                  |
| -------------------- | -------------------------- |
| App page             | `bg` / `text`              |
| App card             | `surface` / `text`         |
| App sidebar          | `surface-strong` / `text`  |
| Dark cover (deck)    | `dark` / white             |
| Dark accent card     | `dark` / `primary-mist`    |
| PDF page             | `bg` / `text`              |
| PDF card             | `surface` / `text`         |

## Migration notes (from v1 gold-on-black)

| v1                          | v2                |
| --------------------------- | ----------------- |
| `#FFB612` (gold primary)    | `#01696F` (teal)  |
| `#0E0E10` (near-black bg)   | `#F7F6F2` (cream) |
| `#1C1C1C` (surface)         | `#F9F8F5`         |
| `#F0F0F0 / #F2F2F2` (text)  | `#28251D`         |
| `#A0A0A0` (muted)           | `#7A7974`         |
| `#4CAF50` (success)         | `#2E7D5B`         |
| `#FF9800` (warn)            | `#B5651D`         |
| `#F44336` (danger)          | `#A8341E`         |
