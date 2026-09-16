---
name: unreal-game-builder
description: Inspect and modify an existing Unreal Engine 5.8 project through its safe JSON harness, including assets, materials, Blueprints, graph nodes, and level actors. Do not use for general Unreal questions or direct binary-asset editing.
---

# Unreal Game Builder

Use the project-local JSON harness for deterministic, auditable Unreal Editor changes.

## Project and contract discovery

1. Starting at the workspace, find the nearest directory containing exactly one `*.uproject`. Stop if the applicable project is ambiguous.
2. Read [references/actions-schema.md](references/actions-schema.md) completely before authoring commands.
3. Treat `Content/Python/execute_actions.py` and its `ACTION_HANDLERS` as authoritative. Use `system.describe_actions` when the installed version may differ from this reference.
4. Before graph work, run `system.capabilities`; continue only when `graph_bridge_available` is true, and use only the returned `node_kinds`.

The runtime files are relative to the project root:

- input: `Content/Python/actions.json`
- output: `Content/Python/result.json`
- executor: `Content/Python/execute_actions.py`

## Change workflow

- Inspect before changing existing state: use `content.list`, `asset.inspect`, `blueprint.inspect`, `blueprint.graph.inspect`, or `level.inspect` as appropriate.
- Build one complete UTF-8 `actions.json`. Use unique IDs and `depends_on` for commands that require earlier results.
- For a broad or uncertain batch, first submit the same document with `dry_run: true`, review the returned plan, then remove `dry_run` and execute.
- Add `project.save` after mutations that must persist. Prefer command-level `save: false` when a later explicit save covers the batch.
- Record the previous modification time of `result.json`, write `actions.json`, wait up to 30 seconds for a change, then read the complete result.
- On failure, report the first failed command and error. Make at most two automatic corrections that remain within the user's request.

## Blueprint graphs

- Inspect the graph before referring to existing nodes or pins.
- Refer to existing nodes by returned GUID. Use `node_id` aliases only for nodes created earlier in the same document.
- Identify function and event nodes by reflected owner class and function name, never localized display titles.
- Let Unreal's K2 schema decide pin compatibility and conversion insertion.
- Compile the Blueprint after graph mutations and save explicitly.

## Native UE 5.8 MCP

Unreal 5.8 can expose its own experimental MCP server when `ModelContextProtocol` and `AllToolsets` are enabled. It is useful for interactive discovery and capabilities not present in the JSON contract. Do not assume it is connected, do not issue overlapping calls, and do not replace a supported deterministic JSON batch with arbitrary execution. Keep the JSON result as the audit record for harness-managed work.

## Safety

- Never edit `.uasset` or `.umap` files directly.
- Never invent actions, operations, node kinds, properties, assets, or pin names.
- Do not add arbitrary Python or shell execution to command JSON.
- Require confirmation immediately before deletion, replacement, or a large change to existing objects. The distributed harness intentionally omits deletion and Blueprint replacement.
- Preserve existing assets. Never set `replace_existing` automatically.
- If `result.json` does not update, ask the user to confirm Unreal Editor is open and the Output Log contains `[AI WATCHER] Watcher started`.
