# App 1.10.2 — Editable planned workouts and clearer swim comparisons

Released 2026-10-09. Use with MCP 1.10.0 (114 tools); the extension archive is unchanged.

## Changes

- Unfinished Today workout cards have a pencil that reopens the shared section-text editor across supported sports. Save updates the selected session in place; completed workouts, neighboring recording links and route settings are protected.
- Plan swim details use a larger credited front/back body-map donut and aligned panels. Estimated intensity stays a five-item vertical key on the left, with stroke distance on the right.
- Compact swim history uses closely spaced vertical columns with chronological dates below, a fixed stroke/work order and shared scales. Distance and percentage views work by session or day over 5/10/20/30/40/60/90 days. Compare stacks Planned above Watch detection.
- Planned includes a recorded written workout description when available, otherwise the saved plan captured at watch association. The underlying sources remain distinct. Missing descriptions are not inferred from unrelated library workouts.
- Named drills use diagonal slashes over their stroke color. Work detail is visible by default and can be hidden; kick/pull retain distinct patterns. Unknown watch drills stay unresolved. Thin zero markers add no distance and do not change percentages or actual segment heights.
- Distance-based swim calendar completion checks use recorded versus prescribed distance, allowing rounding differences. Finishing full distance sooner than estimated duration gets a full check. Duration-based sessions retain time-based checks.
- Fitness Dashboard stroke stacks and legends share the same hierarchy. Wider dashboard bars remain optional follow-up polish.

## Verification and scope

108 Python suites and 17 JavaScript suites pass locally; the paused recovery-calibration suite is skipped. Completed-session protection fixtures include a recorded duration so they exercise specific-session matching. Browser checks covered stacked comparison, persistent controls, typed drill patterns, zero markers and narrow-screen scrolling without page overflow. Cross-platform CI runs after publication; physical-bike verification on Linux/Windows and a physical-bike soak test remain open.

README swim screenshots render actual Hub components with synthetic examples. Existing body-map, mapping and artwork credits and licenses are retained. Personal athlete records, watch/ride files, credentials, private screenshots and the unfinished Halloween planet/game are excluded.

Restart the Hub when no workout is active and refresh Coach after updating. Keep MCP extension version 1.10.0.
