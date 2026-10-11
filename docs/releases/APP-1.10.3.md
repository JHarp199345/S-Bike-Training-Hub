# App 1.10.3 — Training calendar and sport history

2026-10-11. Update the repository and use the existing setup/start launcher. MCP 1.10.0 remains compatible; this update does not publish a new MCP bundle.

## Included

- Full calendar with three months per row, year headings, current date, saved phase colors, past/current/upcoming states, day details and lazy loading of recorded weeks.
- Optional event scheduling through public-directory links, reviewed URL extraction or manual entry. Extracted candidates and ambiguous/missing fields are reviewed before approval. Only explicitly permitted organizer artwork is used.
- Compact upcoming selector, fixed add/remove controls and transitions. Event selection and removal do not regenerate training. Event dialogs retain the calendar navigation context.
- Local-date Today rollover, deferred while an editor or dialog is active.
- Sport training history with lifting benchmarks, dated recorded-session comparisons, completed session/source details and saved strength estimate browsing. Cycling/running include weekly recorded totals and session tables; swimming retains its existing history controls.
- TANK M4 and nominal lifting estimates share kJ for external-work comparison. Shaded bars show assumption ranges, with per-set calculation details and source links. Missing inputs remain unknown. lb × reps remains a separate selectable measure.
- Overall body workload has sport filters and muscle hover highlighting. The original body-highlighter attribution and license remain included.

## Interpretation and limits

TANK estimates use the manufacturer's friction-sled weight equivalents, average speed and assumed friction 0.30–0.60. These are not measured M4 handle forces. Nominal lifting work assumes 0.5 m per repetition. Mechanical work does not measure metabolic calories, training intensity, tissue damage or recovery. Saved strength estimates retain their original dates and are not current capacity tests. No deconditioning forecast is introduced.

Calendar export, event photo albums, recovery forecasting and future-session prediction are not implemented. Event sites may block extraction or omit fields; manual scheduling remains available.

## Privacy

No athlete records, account settings, watch files, private media, local design notes or personal screenshots are included in this update. Design notes remain excluded from Git tracking. Public documentation describes shipped features and their limitations.
