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
Small screens use a native modal navigation drawer and stack collection details.

Forms have visible labels, native controls, error announcements and preserved input
on failure. Loading and empty states distinguish missing data from errors. Controls
have visible keyboard focus and 44px targets. Playwright checks overflow and axe
rules at 360/768/1440px. The R2 source reader pairs extracted passages with physical
PDF page images and evidence-colored location highlights. Below 1100px, native
buttons switch between text and source; returning restores the selected passage's
focus. TXT passages preserve Unicode and original line numbers. Answers support an
IME-aware composer and exact source citations. At 1100px and above, an accessible
range control adjusts the source panel width between 320 and 480px, clamped to
available space; the browser remembers the preference when storage is available.
Below 1100px, a citation opens a separate source view. Back/Escape restores focus
to its citation button. Retained earlier sources carry an Older version label.

Owner evaluations use comparison tables with definitions and denominators, then
expected/retrieved evidence and the actual-answer state. Missing measurements stay
explicitly unmeasured. Synthetic development/frozen diagnostics are separate from current
workspace data. Browser checks with mocked API responses cover 360/768/1200/1440px,
navigation, focus return, overflow and axe rules; this is not live backend acceptance.

Each report supplies its own metric definitions: R4 uses document groups, R8 exact
canonical spans/versions. Cases without permitted gold show Abstention not measured
and do not appear in the incomplete-evidence filter. Demo screenshots identify their
mocked answers/comparison data and are preserved in `docs/assets/r8`.
