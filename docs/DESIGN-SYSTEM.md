# Design system foundation

The implemented tokens live in `apps/web/src/app/globals.css` and follow blueprint
section 7: parchment `#F3F1E9`, white surfaces, ink `#22342B`, muted `#5B685F`,
forest actions `#255D43`, and evidence `#F4E3A4` with ink `#493C14`.
Control borders use `#7A887E`; dividers use `#D7DDD4`.

Manrope is the interface face, Source Serif 4 the reading face, and Noto Sans
Devanagari the Nepali fallback. Fonts are bundled locally through Fontsource;
builds and page loads do not request Google Fonts. Panels use an 8px radius.
Focus is a 3px green outline with white separation. No animation is needed yet.

The starter has landmarks, a skip link, responsive wrapping, and an honest unavailable
state. The eventual three-pane reader, citation focus return, collection navigation,
and IME-aware composer are future milestones, not represented by inactive controls.
