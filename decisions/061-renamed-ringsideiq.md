# 061. The product is RingsideIQ

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6
- **Amended by**: ADR-064 — fixes from the full review

## Context

The owner renamed the product from Alion to RingsideIQ (15 Oct 2026) and asked for
a new logo. Of three drawn concepts (ropes and pulse, the ring from above, the
corner) the owner chose the first.

## Decision

- **The mark** (`components/RingsideLogo.tsx`; `public/brand/ringsideiq-mark.svg`):
  a ring seen from ringside — two corner posts and three ropes, the middle rope
  carrying a heartbeat — in near-black on the brand gradient (violet `#a78bfa` →
  emerald `#34d399`) the dashboard already uses. The wordmark is "Ringside" with
  "IQ" in emerald. The same drawing is the browser-tab icon (`app/icon.svg`, there
  was none), and `scripts/brand_icons.py` renders it into the phone apps' icons and
  splash screens. Those were Capacitor's placeholders.
- **What people read says RingsideIQ**. That covers:
  - on screen: the page title, the home page, the sidebar and phone menu, the
    disclaimer and safety notes, the privacy page, and staff and gym invitations;
  - elsewhere: the phone camera page, downloaded file names (`ringsideiq-….csv`),
    the API's docs title, and the phone apps' names and camera prompt.
- **The terms** say "RingsideIQ (formerly Alion)" at the first mention.
  `TERMS_VERSION` stays `draft-4`: a new name doesn't change what anyone agreed to,
  so nobody is asked to accept again.
- **What stays `alion`**, because renaming it would break things or rewrite
  history:
  - the `ALION_*` settings and `data/alion.db`;
  - the browser's stored keys (`alion.token` and the rest), whose rename would
    sign everyone out and forget their choices;
  - package and folder names;
  - the phone app id `ai.alion.app`, since a new id is a different app to the
    stores and to installed phones;
  - the decision records, the dated research notes and the study documents in
    `docs/studies/` (the dissertation, the literature review and the RQ2
    protocol), which are the owner's to rename.

## Consequences

- An ethics board that approved a consent text naming Alion may need to hear of
  the new name; the study documents still say Alion until the owner changes them.
- `brand_icons.py` needs `rsvg-convert` and Pillow; run it again if the mark changes.
