# App + MCP 1.2 integration

MCP 1.2 adds `get_program`, `preview_program`, `apply_program`, and `get_progress_evidence`. Tools use the same local app APIs as the browser. Preview does not save; Apply is an explicit athlete-approved action. Reported lifting anchors and starter options go in the `fields` object.

The source and bundle manifest are updated together. Build locally with `mcpb/build.sh`. The resulting `.mcpb` is intentionally ignored by Git; publish it as a release asset before distributing the new download URL in server.json. The server metadata SHA matches the built artifact for this revision.

The older installed 1.1 bundle retains its older tool list until replaced. A Git checkout of the new app does not automatically replace an assistant's installed bundle. An external AI receives data returned by tools under its own provider policies.

Verification: real program API tests cover preview isolation, three scenarios, prescribed weights, apply preservation and MCP dispatch. Existing MCP protocol tests cover tool listing, handshake and scratch-bridge execution.
