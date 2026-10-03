# MCP capability review — October 2, 2026

## What the interface must enable

The MCP server is the assistant’s working interface to the Hub. It cannot make an uncertain recovery model medically accurate, but it can make planning more reliable by exposing inputs, assumptions, constraints, forecasts, actions and verification. A useful loop is:

**Read goals and current state → investigate relevant evidence → preview alternatives → review constraints → obtain approval → apply → verify → compare outcomes.**

The athlete should not need to copy large tables into chat, repeat constraints after every step, or repair configuration files. The assistant should have a compact overview and bounded access to underlying evidence. More tools alone do not establish better coaching.

## Verified in this revision

- Claude Desktop installed MCP 1.2.0, accepted its runtime requirements, enabled the extension and discovered all 52 tools using the default local Hub address. No manual JSON configuration or extra Python packages were needed.
- Claude Desktop also installed the 1.2.1 update with the existing local address and permissions retained; its 20 read-only and 32 write/delete tools were discovered. The installed server matched the release source byte-for-byte and passed the same isolated workflow.
- Version 1.2.1’s packaged server passed an isolated workflow on macOS’s stock Python 3.9 with a minimal PATH and an unrelated working directory: program read, three-scenario preview, focused detailed preview, apply, check-in and progress evidence.
- The preview test confirms that the saved coach file remains unchanged. Empty Apply requests now fail clearly. Applying the scratch program saves its goal and preserves the app’s existing API behavior.
- A six-week preview previously returned about **5.4 MB**. The equivalent compact preview now returns **18,032 bytes**; two days of detailed prescriptions and projections return **33,559 bytes**. Apply returns **18,032 bytes** and Today **10,862 bytes** in the same synthetic fixture. These are measured test results, not universal response-size guarantees.
- Compact comparisons preserve assumptions, unknown metrics, scenario summaries, and grouped load-limit flags including peak, limit, first flagged date and count. The selected scenario’s detailed daily metrics and workouts remain available through `detail_start` and `detail_days` (1–7).
- Program tools now advertise typed common inputs and require a nonempty `fields` object. Tool annotations distinguish reading from changes conservatively: Today, calibration and skills reads can also update derived local records, so they are not advertised as strictly read-only.
- Server instructions explicitly ask the assistant to retain goal, phase, time, priorities, holds and unresolved calibration gaps; re-read state after a long discussion; inspect focused forecast evidence; distinguish assumptions from measurements; and read back the saved program after applying.

Protocol, real program API and packaged-server tests passed. This verifies interface behavior, not clinical accuracy or the quality of every model’s coaching decisions. Client/model evaluations are a separate gate.

## Where the assistant can investigate today

| Question | Existing tools / evidence |
|---|---|
| What are we training toward, and what phase are we in? | `get_program`, `get_today`, `get_training_block` |
| What happened, and how did it feel? | `get_rides`, `get_ride_story`, `get_checkins`, `get_insights` |
| Why is training constrained? | `get_load`, `get_today`, sport-specific programming, lifting guidance and calibration |
| What session templates and rules are available? | `get_programming`, `get_lifting`, `get_skills`, `get_calibration` |
| How would three starter workloads differ? | `preview_program`, then a focused detailed preview |
| Can the assistant write and verify the program? | `apply_program`, followed by `get_program` and relevant daily reads |
| Is performance actually changing? | `get_progress_evidence`, `get_aerobic`, follow-up reports and weekly review |

Some older evidence tools still return substantial payloads. The public README explains the load formulas and their limitations; there is not yet a dedicated metric-explanation tool providing a per-reading calculation trace.

## Priorities for the next interface revision

### 1. Apply the exact reviewed draft

Currently Apply rebuilds a proposal from fields. It does not accept a locked draft ID or check whether athlete data changed between preview and save. Implement a server-side draft ID, input/state revision, expiry, and an idempotent Apply operation. If state changed, return a readable conflict and require a new preview. Verify the saved phases and detailed sessions, not merely a success message.

### 2. Inspect the saved calendar in small ranges

Add a bounded calendar read for existing prescriptions, actual completions and projections. Preview detail describes a proposed scenario, not a universal read of every saved workout. Include stable session IDs and the source of each prescription so the assistant can target one session without rebuilding unrelated weeks.

### 3. Explain a reading from its evidence

Expose metric definitions, units, model version, measured inputs, assumed inputs, session contributions, recovery behavior and uncertainty on request. Include the applicable formula and source references, but do not portray assumed regional allocations as measured tendon forces. This is how the assistant can investigate what a summary means without receiving the entire data history at once.

### 4. Expose the existing adaptation workflow deliberately

The app has session-report, progression comparison, symptom resolution and phase-profile APIs that are not all represented by dedicated MCP tools. Add explicit read/compare/commit operations rather than a generic arbitrary-API tool. Keep athlete authorization, current running holds, phase purpose and cross-sport overlap visible. A report that an intended recovery session felt easy is not automatically a reason to add load.

### 5. Make forecast and execution agree

A synthetic starter cycling prescription had three power steps totaling 17 minutes, but the ride widget constructed its generic warm-up/ramp/main/cool-down layout instead. Investigate that handoff and verify planned steps, saved workout blocks, player execution and forecast use the same prescription. This is an app integration concern as well as an MCP concern.

### 6. Evaluate complete coaching tasks

Use synthetic athlete fixtures and score outcomes, not just successful tool calls: recovery-week “too easy,” a current running hold, shoulder discomfort, a near event, missing lift anchors, delayed adverse response, an intervening workout before Apply, and preserved completed history. Measure whether the assistant chooses relevant evidence, respects constraints, proposes an appropriate change, obtains approval and verifies the result. Repeat across the desktop assistants intended for users.

## Audience fit

Keep installation simple, retain ordinary approval controls, use the same local calculators as the UI, and show a clear diff before major plan changes. Routine exploration should be read-only wherever possible. The Hub runs locally; an optional external AI receives whatever training context its tools return under that provider’s policies. The bundle requires the Hub to be running and does not make localhost accessible to remote cloud sessions.

## Design references

- [Anthropic: Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents): clear tool purposes, meaningful context and responses, and evaluation with realistic tasks.
- [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools): tool schemas, results, error reporting and annotations. Annotations are hints, not security enforcement.
- [MCP bundle manifest](https://github.com/modelcontextprotocol/mcpb/blob/main/MANIFEST.md): runtime requirements and desktop configuration.
- [Claude Desktop local MCP setup](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop): local servers and desktop installation.

These references support interface design. They do not validate the Hub’s proprietary block scale or its recovery forecasts.
