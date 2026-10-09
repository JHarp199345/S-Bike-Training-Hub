# App + MCP 1.3 integration

Version **1.5.0** exposes 66 tools through the same local APIs used by the browser. [Download the bundle](https://github.com/JHarp199345/S-Bike-Training-Hub/releases/download/mcp-v1.5.0/s-bike-hub-mcp-1.5.0.mcpb). See the [README installation instructions](../README.md#install-the-claude-desktop-extension).

## Planning workflow

1. Read `get_program`, then inspect relevant saved sessions with `get_training_calendar` (1–14 days).
2. Investigate a reading with `explain_training_reading`; inspect feedback and unresolved symptoms with `get_adaptation_review`.
3. Call `preview_program` with `fields`. Request 1–7 days of detailed prescriptions through `detail_start` and `detail_days`.
4. Review alternatives, assumptions, holds and missing anchors with the athlete.
5. After approval, call `apply_program` with the returned `draft_id`. Read back `get_program` and the saved calendar.

Preview caches the exact proposal separately from training records for six hours, retaining up to eight drafts. Apply rejects expired or missing drafts, changed coach/profile/activity/workout inputs, changed calculation source versions, and starts in the past. It applies the stored proposal without rebuilding. Retries of retained applied drafts return an existing receipt. Completed history is preserved. These safeguards cover app requests; arbitrary external file edits during an operation are not a supported concurrency mechanism.

**Update the Hub and bundle together.** Field-based Apply from older bundles is no longer accepted. Version 1.3 refuses Apply against an app without reviewed-draft support. Updating Git does not replace an installed desktop extension. The Hub must be running locally.

Calendar responses expose prescriptions, completions, holds and future projections. Past forecasts are not recreated from today's baseline. Explanation responses include formulas, source hashes, baseline inputs, contributors and unknown values; regional allocations and recovery curves remain estimates.

## Verification and building

The packaged 1.3 server passed synthetic API workflows on stock macOS Python 3.9 with an isolated environment. Previous 1.2 Desktop installation was verified; 1.3 Desktop installation and live assistant decision quality remain separate checks. The optional real-assistant evaluation was blocked by an expired Claude sign-in.

Build with `sh mcpb/build.sh`. Bundles are release assets, ignored by Git; `server.json` records SHA-256. Run `tests/test_mcp_bundle.py` against the archive. Optional `tests/eval_mcp_coaching.py` uses a signed-in Claude Code assistant with synthetic data, disabled built-in tools and preview-only permissions. It consumes the configured assistant's usage allowance and is excluded from routine tests.

The Hub stores athlete data locally. Context supplied to external AI is governed by that provider's policies; remote cloud sessions cannot reach a Mac's localhost directly.

MCP 1.4 also provides guided bike setup and recent-week/missed-session tools. The exact-draft workflow is retained. See [bike setup](bike-setup.md).

MCP 1.5 adds `get_coaching_review`, `preview_coaching_change` and `apply_coaching_change`. See [forecast/capacity review](coaching-review.md). Install the matching updated app; the new endpoints are not available on older servers.
