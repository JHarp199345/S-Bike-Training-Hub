# App 1.10.1 — Windows watch imports corrected

Released 2026-10-09. Use with MCP 1.10.0 (114 tools).

Windows locks an open temporary file. Watch import validation now closes its writer before the FIT/TCX reader opens the file, and removes the temporary validation directory after success or failure. Manual and assistant imports share this correction. Duplicate detection and filename collision protection remain in place.

All [App 1.10.0 improvements](APP-1.10.0.md) are included: workout records, swim timing, compact Plan history, Fitness Dashboard comparisons, energy units, library cards and normal ride/media controls. The unfinished Halloween world and athlete data remain excluded.

The initial 1.10.0 automated checks passed on macOS and Linux and identified the Windows import failure. The focused import tests pass locally after this correction; the cross-platform CI results are available with this release. Physical-bike verification on other systems is not claimed.

Restart the Hub when no workout is active and refresh Coach after updating. The MCP archive is unchanged: keep extension version 1.10.0.
