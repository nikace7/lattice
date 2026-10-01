# Design system foundation

The implemented tokens live in `apps/web/src/app/globals.css` and follow blueprint
section 7: parchment `#F3F1E9`, white surfaces, ink `#22342B`, muted `#5B685F`,
forest actions `#255D43`, and evidence `#F4E3A4` with ink `#493C14`.
Control borders use `#7A887E`; dividers use `#D7DDD4`.

Manrope is the interface face, Source Serif 4 the reading face, and Noto Sans
Devanagari the Nepali fallback. Fonts are bundled locally through Fontsource;
builds and page loads do not request Google Fonts. Panels use an 8px radius.
Focus is a 3px green outline with white separation. No animation is needed yet.

The workspace follows a quiet reading-room direction: collection navigation on
the left, the working list in the center, details and permissions on the right.
Sign-in and the workspace chooser share the same typography and restrained colors.
Small screens use a collapsible navigation rail and stack collection details.

Forms have visible labels, native controls, error announcements and preserved input
on failure. Loading and empty states distinguish missing data from errors. Controls
have visible keyboard focus and 44px targets. Playwright checks overflow and axe
rules at 360/768/1440px. The future source reader, citation focus return and
IME-aware composer remain outside this phase.
