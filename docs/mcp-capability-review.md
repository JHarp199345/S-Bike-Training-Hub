# MCP capability review — October 2, 2026

## What the interface must enable

The MCP server is the assistant’s working interface to the Hub. It cannot make an uncertain recovery model medically accurate, but it can make planning more reliable by exposing inputs, assumptions, constraints, forecasts, actions and verification. A useful loop is:

**Read goals and current state → investigate relevant evidence → preview alternatives → review constraints → obtain approval → apply → verify → compare outcomes.**

The athlete should not need to copy large tables into chat, repeat constraints after every step, or repair configuration files. The assistant should have a compact overview and bounded access to underlying evidence. More tools alone do not establish better coaching.

## Verified in MCP 1.3.0

- 55 tools, including new saved-calendar, reading-explanation and adaptation-review tools.
- Exact cached draft application, six-hour expiry, state conflict detection, retained retry receipts and preservation of completed history. Field-only Apply is rejected. The browser and MCP use the same implementation.
- Tests reject intervening check-ins, calendar edits, recorded activities, profile changes and workout-library changes. Applying a proposal succeeds even with proposal generation disabled, proving it does not rebuild.
- Saved calendar inspection exposes actual prescriptions, completions, restrictions, unresolved symptoms and bounded projections. Reading explanations expose implemented formulas, source hashes, assumptions, baseline inputs and contributions. Unknown readings remain unknown.
- Synthetic coaching scenarios verify recovery/taper “too easy” feedback preserves purpose, build feedback can become a progression candidate, shoulder and heart-rate concerns become regression candidates, running holds remain visible, missing lifting anchors block application, and near-event plans respect taper context. Existing progression tests cover delayed responses and overlap.
- The actual packaged server passed an isolated workflow using stock macOS Python 3.9: program, preview, detailed preview, exact apply, check-in, Today, progress evidence, calendar, explanation and adaptation review.
- Fixture response sizes: compact preview **18,417 bytes**, two-day detailed preview **41,748 bytes**, Apply **18,270 bytes**, one-week calendar **28,119 bytes**, reading explanation **2,768 bytes**. These are measurements, not universal limits.
- The full Python suite passed **55 of 56 files**. The remaining existing headless QR-image scanning failure is outside the changed planning code.

Earlier 1.2 releases were installed and discovered in Claude Desktop. The 1.3 Desktop update has not yet been retested. Optional real-assistant scenarios are implemented, but the attempted run was blocked by an expired Claude OAuth sign-in. Deterministic scenario tests do not establish actual assistant decision quality or validate the training model.

## Evidence available to the assistant

| Question | Tools |
|---|---|
| Goals, phases and current constraints | `get_program`, `get_today`, `get_training_block` |
| Saved sessions, completions and projections | `get_training_calendar` |
| Formula, baseline, contributors and uncertainty | `explain_training_reading` |
| Feedback, unresolved symptoms and adaptation decisions | `get_adaptation_review` |
| Alternatives and detailed prescriptions | `preview_program` |
| Apply the reviewed proposal and verify | `apply_program`, `get_program`, `get_training_calendar` |
| Performance evidence | `get_progress_evidence`, `get_aerobic` |

Preview writes a separate local draft cache, so it is conservatively annotated as a write operation. Calendar, explanation and adaptation reads do not save coach records. Older derived-state reads retain conservative annotations.

## Remaining work

- Expand dedicated write tools for existing session reports, symptom resolution and phase-profile review; adaptation reading is now available.
- Verify cycling starter prescription → workout player → forecast consistency. An earlier synthetic prescription exposed a generic player-layout handoff mismatch; this update does not resolve that integration issue.
- Complete actual assistant scenario evaluations after sign-in is restored, then repeat across supported desktop assistants. Evaluate evidence selection, constraints, approval and verification, not just tool-call success.
- Some older evidence responses remain large. Continue bounding detail requests while preserving constraints and uncertainty.

## Audience fit

Keep installation simple, retain ordinary approval controls, use the same local calculators as the UI, and show a clear diff before major plan changes. Routine exploration should be read-only wherever possible. The Hub runs locally; an optional external AI receives whatever training context its tools return under that provider’s policies. The bundle requires the Hub to be running and does not make localhost accessible to remote cloud sessions.

## Design references

- [Anthropic: Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents): clear tool purposes, meaningful context and responses, and evaluation with realistic tasks.
- [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools): tool schemas, results, error reporting and annotations. Annotations are hints, not security enforcement.
- [MCP bundle manifest](https://github.com/modelcontextprotocol/mcpb/blob/main/MANIFEST.md): runtime requirements and desktop configuration.
- [Claude Desktop local MCP setup](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop): local servers and desktop installation.

These references support interface design. They do not validate the Hub’s proprietary block scale or its recovery forecasts.

## October 3 cloud-branch review and MCP 1.4

The training-journey branch adds bike setup, phase-specific training progression and peak weeks, missed-session reasons/recent-week evidence, watch uploads, calendar improvements and a synthetic 12-week journey harness. MCP now exposes 63 tools. The branch head passed GitHub's macOS and Linux checks. Local testing passed 60 of 61 files, with the existing QR-image scanning failure.

Review tightened running learning: protected, legacy and existing return-to-run protocols retain their reviewed block scale; automatic evidence-based rescaling is limited to ordinary training outside that protocol. Initial capacity growth now requires genuinely clean reports rather than merely reports below the roughness cutoff. The 60% plateau review gate remains. The global 50-day default is removed for ordinary users; an athlete-specific minimum remains supported and should be retained for athletes who requested it.

The synthetic journey runs from its own copied app directory; updating source does not alter an already-running copy. Live personal servers must be restarted deliberately after their files are updated. No personal records are part of the release.

## MCP 1.5 coaching review

Two-week cross-sport forecast context, exact reviewed calendar replacements and evidence-supported running/regional lifting capacity reviews are available through three new tools (66 total). Benchmark grades now propose review instead of silently increasing capacity on a read. See [workflow, provisional policies and limits](coaching-review.md). Local full tests: 61/62 files pass; the existing QR decode issue remains. New scenario and installable-bundle tests pass. The running personal app is not updated or restarted by this release.
