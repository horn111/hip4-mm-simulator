# Design System

## Direction

Light analytical evidence surface. The physical scene is a grant reviewer at a
desk in daylight, scanning technical proof between other applications. The
composition follows the approved Causal walkthrough direction, with compact
instrument controls and an evidence ledger below it.

## Color

Use OKLCH tokens only:

- Background: `oklch(1 0 0)`
- Surface: `oklch(0.97 0.005 260)`
- Raised surface: `oklch(0.94 0.008 260)`
- Ink: `oklch(0.20 0.015 260)`
- Muted ink: `oklch(0.45 0.015 260)`
- Rule: `oklch(0.88 0.008 260)`
- Primary / sell: `oklch(0.53 0.19 354.5)`
- Primary soft: `oklch(0.95 0.035 354.5)`
- Buy / pass: `oklch(0.45 0.12 155)`
- Buy soft: `oklch(0.95 0.025 155)`
- Information: `oklch(0.46 0.12 255)`

Saturated fills use white text. Buy/sell/pass states always include a label or
icon, never color alone.

## Typography

Use Geist Sans for interface and explanatory copy and Geist Mono for prices,
sizes, timestamps, hashes, IDs, and aligned metrics. Use regular, medium,
semibold, and bold only. Body text is at least 1rem with 1.6 line height; hero
and section headings use bounded fluid sizes and balanced wrapping.

## Spacing and layout

Use a 4px-derived scale: 4, 8, 12, 16, 24, 32, 48, 64, and 96px. Related data
stays tight; major narrative sections use generous separation. The main content
is capped at 1240px. The three-stage causal visualization is horizontal above
1024px, two-column at tablet widths where useful, and a vertical sequence on
mobile.

## Components

Controls use familiar button, select, tooltip, badge, and disclosure patterns.
The L2 ladder, queue strip, event rail, causal connector, balances, and
invariant ledger are custom semantic components. Avoid nested cards and repeated
icon-heading-copy tiles.

## Motion

Only replay state changes move. Use 180-240ms ease-out-quart transitions for
queue depletion, event focus, and fill appearance. Playback uses 2.4s, 1.2s,
and 0.6s intervals. Reduced motion removes interpolation while preserving every
state and control.
