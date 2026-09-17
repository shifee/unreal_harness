# Unreal Codex Harness

A portable, safety-focused JSON automation layer and project-local Codex Skill for Unreal Engine 5.8. It watches `Content/Python/actions.json`, validates the whole batch before mutation, executes supported editor operations serially, and atomically writes a structured `result.json` audit record.

This project targets Unreal Engine **5.8**. UE 5.7 is no longer supported.

## Design

- Deterministic JSON batches with dependencies, dry-run plans, bounded output, and stable result envelopes.
- Declarative `$repeat`, `$mirror`, and `$grid` recipe expansion with `fail`, `reuse`, and `update` conflict modes.
- Editor Undo transactions for mutating actions.
- Inspection-first asset, Blueprint, graph, material, and level workflows.
- A small C++ graph bridge for K2 functionality that Unreal Python does not expose reliably.
- No arbitrary Python, shell execution, asset deletion, or silent Blueprint replacement.
- Optional coexistence with UE 5.8's built-in experimental Unreal MCP server.

The design review behind v0.1 is documented in [docs/IMPLEMENTATION_RESEARCH.md](docs/IMPLEMENTATION_RESEARCH.md).

The accepted long-term structure is a universal reflection/asset/graph core with capability discovery, declarative recipes, and backend adapters for specialized Unreal subsystems. See [target architecture](docs/TARGET_ARCHITECTURE.md) and the staged [technical roadmap](docs/ROADMAP.md).

## Requirements

- Unreal Engine 5.8.
- An existing project with one `.uproject` in its root.
- Unreal plugins `PythonScriptPlugin`, `EditorScriptingUtilities`, and the installed `UnrealCodexGraph` project plugin.
- Python 3.9+ for the installer and validator; they use only the standard library.
- A UE 5.8-supported C++ toolchain to build the graph bridge (Visual Studio 2022 on Windows).
- Codex opened at the Unreal project root for project-local skill discovery.

The optional native MCP integration uses the UE 5.8 `ModelContextProtocol` and `AllToolsets` plugins. Unreal MCP is experimental and listens on loopback without authentication by default; do not expose it to a network.

## Install

```powershell
git clone https://github.com/shifee/unreal_harness.git
cd unreal_harness
py scripts/install.py --project "C:/Path/Project/Project.uproject"
```

Project discovery and safe update modes:

```powershell
py scripts/install.py
py scripts/install.py --project-dir "C:/Path/Project"
py scripts/install.py --dry-run --project "C:/Path/Project/Project.uproject"
py scripts/install.py --force --project "C:/Path/Project/Project.uproject"
```

Without an explicit path, the installer checks the current directory, its parents, and a depth-limited subtree. It never scans a whole drive. Existing files are skipped; `--force` creates timestamped sibling backups before replacement.

To let the installer enable the required plugins (with a `.uproject` backup):

```powershell
py scripts/install.py --project "C:/Path/Project/Project.uproject" --enable-plugins
```

To additionally enable UE 5.8's native MCP server and default toolsets:

```powershell
py scripts/install.py --project "C:/Path/Project/Project.uproject" --enable-native-mcp
```

You can also enable plugins manually in **Edit → Plugins**. Restart Unreal after changing plugins.

## First run

1. Open the project in UE 5.8 and allow the `UnrealCodexGraph` Editor plugin to build if prompted.
2. In **Window → Developer Tools → Output Log**, confirm:

   ```text
   [AI WATCHER] Watcher started
   ```

3. Open the project root in Codex and try:

   ```text
   Use $unreal-game-builder to inspect the current level, place three instances of an existing Blueprint actor in a row, and save the level.
   ```

The watcher treats the existing `actions.json` as already seen at startup. A client must write a new complete document to trigger execution.

## JSON contract

```json
{
  "format_version": "1.0",
  "dry_run": false,
  "commands": [
    {
      "id": "inspect_level",
      "action": "level.inspect",
      "arguments": {"limit": 100}
    }
  ]
}
```

The executor rejects duplicate IDs, unknown actions, forward/missing dependencies, malformed arguments, and batches larger than 200 commands before any mutation occurs. `dry_run: true` returns the execution plan without running commands.

For repeated constructions, a top-level `recipes` array can generate ordinary commands and nested operation lists with `$repeat`, `$mirror`, and `$grid`. Recipe conflict modes make reruns explicit: `fail` rejects an existing destination, `reuse` keeps it, and `update` applies supported changes without creating duplicates. See `examples/patterned-castle.json` and the installed command reference for the exact schema.

Supported families:

- discovery: `system.capabilities`, `system.describe_actions`
- content: `content.create_folder`, `content.list`, `asset.inspect`
- materials: `material.create`, `material.inspect`, `material_instance.create`, `material_instance.set_parameters`
- Blueprints: `blueprint.create`, `blueprint.inspect`, `blueprint.compile`, `blueprint.edit`
- graphs: inspect, add universal node kinds, connect pins, set literal pin values
- levels: inspect actors, spawn actors, set actor transforms and reflected properties
- persistence: `project.save`

Graph node kinds in v0.1 are `function_call`, `event`, `branch`, `sequence`, `reroute`, `self`, `variable_get`, `variable_set`, and `dynamic_cast`. Query `system.capabilities` rather than assuming the list.

See the installed `references/actions-schema.md` for exact shapes. `examples/numeric-blueprint.json` remains a complete graph example.

## UE 5.8 native MCP

The harness and native Unreal MCP serve different purposes:

- the JSON harness is the deterministic batch, dependency, Undo, and audit layer;
- native MCP is useful for interactive tool discovery and engine-provided toolsets.

To configure native MCP, enable **Unreal MCP** and **All Toolsets**, enable Auto Start under Editor Preferences, then use the editor console:

```text
ModelContextProtocol.GenerateClientConfig Codex
```

The default endpoint is `http://127.0.0.1:8000/mcp`. Unreal serializes tool execution on the game thread, so clients must not issue overlapping calls.

## Validation

```powershell
py scripts/validate_install.py "C:/Path/Project"
```

Validation checks required files, JSON, Python syntax, skill frontmatter, action-reference drift, forbidden source-machine paths, and required plugins. It does not start Unreal Editor or change the project.

For an end-to-end test in a dedicated UE 5.8 project, first install the current harness and close the interactive editor instance for that project, then run:

```powershell
py scripts/run_ue_smoke_test.py --project "C:/Path/TestProject/TestProject.uproject"
```

The smoke test checks the capability snapshot, creates a uniquely named material and Actor Blueprint, builds and compiles a BeginPlay → Print String graph, spawns the actor in the commandlet world, and verifies the mutation audit. Test assets are intentionally retained under `/Game/CodexHarnessSmoke/<run>` for inspection; the original `actions.json` and `result.json` are restored.

## Install only the Codex Skill

```text
Use $skill-installer to install from https://github.com/shifee/unreal_harness/tree/main/.agents/skills/unreal-game-builder
```

This installs only the instructions, not the Unreal Python harness or graph plugin. Use `scripts/install.py` for the complete integration.

## Update

```powershell
git pull
py scripts/install.py --project "C:/Path/Project/Project.uproject" --force
py scripts/validate_install.py "C:/Path/Project"
```

Review timestamped backups before removing them.

## Troubleshooting

- No watcher message: confirm the required plugins are enabled, restart Unreal, and inspect the Output Log.
- `result.json` does not change: make sure Unreal Editor is open and `actions.json` is valid JSON.
- Graph bridge unavailable: rebuild the project plugin with UE 5.8, restart, then run `system.capabilities`.
- Multiple projects found: pass the exact `.uproject` with `--project`.
- Native MCP unavailable: check `LogModelContextProtocol`, confirm Auto Start, and keep the endpoint on loopback.

## Safe removal

Close Unreal Editor and review local modifications before removing:

```text
Content/Python/execute_actions.py
Content/Python/init_unreal.py
Content/Python/actions.json
.agents/skills/unreal-game-builder/
Plugins/UnrealCodexGraph/
```

`Content/Python/result.json` is runtime output. Do not remove surrounding directories if they contain unrelated files. Plugin entries in `.uproject` are not removed automatically.

## License

MIT. See [LICENSE](LICENSE).
