# UE 5.8 Harness Implementation Research

This review informed v0.1. No third-party source files were copied. The project adopts architectural patterns and reimplements them against the UE 5.8 API in its existing style.

## Selected references

- [Epic Unreal MCP for UE 5.8](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor): in-editor loopback HTTP MCP, game-thread serialization, toolset discovery, and compact tool-search mode.
- [GenOrca/unreal-mcp](https://github.com/GenOrca/unreal-mcp) (Apache-2.0): domain catalogs, generated contract checks, per-action in-editor tests, soft optional-plugin dependencies, and editor transactions.
- [SunGrow/ue-blueprint-extractor](https://github.com/SunGrow/ue-blueprint-extractor) (Apache-2.0): inspection-first workflows, structured envelopes, explicit saving, bounded tool profiles, and verification as a separate phase.
- [IvanMurzak/Unreal-MCP](https://github.com/IvanMurzak/Unreal-MCP) (Apache-2.0): schema validation, stable manifests, game-thread dispatch, capability gating, and tests at the Unreal boundary.
- [avdo403/UnrealMCP](https://github.com/avdo403/UnrealMCP): broad Blueprint graph taxonomy and schema-mediated pin connections. Its transport and arbitrary execution surface were not adopted.

## Adopted

- Validate the entire command document before mutation.
- Make every mutating action an Unreal Undo transaction.
- Provide runtime action/capability discovery instead of relying only on prose.
- Keep read/inspect operations first-class and bound list sizes.
- Use a compact universal graph-node action with a typed `kind`, not one JSON action per node.
- Keep persistence explicit with `project.save` and expose dry-run plans.
- Write `result.json` atomically with run IDs and timestamps.
- Treat optional engine plugins as soft capabilities.

## Deliberately not adopted

- Arbitrary Python or shell execution: too much authority for a narrowly scoped harness.
- Custom TCP/SignalR/Node/.NET sidecars: UE 5.8 already ships a local MCP server, while file-based JSON remains simpler and auditable.
- Hundreds of one-off actions: they increase schema drift and context cost.
- Cloud relay and remote binding: unnecessary for local editor automation and materially expands the attack surface.
- Silent deletion, replacement, or bulk mutation commands.
- Duplicating UE 5.8 native MCP toolsets inside this repository.

## Resulting boundary

The JSON harness owns deterministic batches, dependencies, Undo, bounded inspection, and audit output. UE 5.8 native MCP may coexist for interactive discovery and engine-provided toolsets. The custom C++ bridge is limited to K2 graph operations that are not reliably available through Unreal Python.
