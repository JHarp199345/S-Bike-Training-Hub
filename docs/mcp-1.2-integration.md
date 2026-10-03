# App + MCP 1.2 integration

Version **1.2.1** exposes 52 tools, including `get_program`, `preview_program`, `apply_program`, and `get_progress_evidence`. Tools use the same local app APIs as the browser. Preview does not save; Apply is an explicit athlete-approved action. Reported lifting anchors and starter options go in the `fields` object.

[Download 1.2.1](https://github.com/JHarp199345/S-Bike-Training-Hub/releases/download/mcp-v1.2.1/s-bike-hub-mcp-1.2.1.mcpb) or read the [release notes](https://github.com/JHarp199345/S-Bike-Training-Hub/releases/tag/mcp-v1.2.1). Installation instructions are in the [README](../README.md#install-the-claude-desktop-extension).

Program summaries preserve scenario comparisons and load flags while avoiding multi-megabyte responses. Pass `detail_start` and `detail_days` (1–7) to `preview_program` for the selected scenario’s workouts and projected readings. Empty Apply requests are rejected. Apply currently regenerates from fields; it does not lock an exact reviewed draft.

Claude Desktop installation and tool discovery were verified for 1.2.0 and the 1.2.1 update. The 1.2.1 packaged workflow was tested with macOS’s stock Python 3.9, a minimal PATH, no site packages and isolated synthetic athlete data. See the [capability review](mcp-capability-review.md) for measured response sizes, evidence available to the assistant and remaining gaps.

Build locally with `sh mcpb/build.sh`. The `.mcpb` is ignored by Git and distributed as a release asset; `server.json` records its SHA-256. Run `tests/test_mcp_bundle.py` to test the actual archive when present, or the source bundle layout in a fresh checkout. Set `S_BIKE_TEST_INSTALLED_SERVER` to an installed server path to verify it matches the tested source.

An app Git update does not automatically replace an assistant’s installed bundle. The Hub must be running on the Mac. External AI receives the training context returned by tools under its provider’s policies.
