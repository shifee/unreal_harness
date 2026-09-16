# Unreal Codex Harness

A portable JSON command harness and project-local Codex skill for making controlled Unreal Editor changes. The harness watches `Content/Python/actions.json`, executes supported actions inside Unreal Editor, and writes structured outcomes to `Content/Python/result.json`.

The current release was extracted from and tested against an Unreal Engine 5.7 project. It is not claimed to work with every Unreal Engine 5 release because Unreal's Python API can change between versions.

## Requirements

- An existing Unreal Engine 5 project with one `.uproject` in its root.
- Unreal plugins `PythonScriptPlugin` and `EditorScriptingUtilities` enabled.
- Python 3.9 or newer for the installer and validator (standard library only).
- Codex opened at the Unreal project root for project-local skill discovery.

The installer never copies `.uasset`, `.umap`, `Saved`, `Intermediate`, `DerivedDataCache`, game assets, secrets, or a previous machine's `result.json`.

## Clone and install

```powershell
git clone https://github.com/OWNER/unreal-codex-harness.git
cd unreal-codex-harness
py scripts/install.py --project "C:/Path/Project/Project.uproject"
```

Project discovery is also available:

```powershell
py scripts/install.py
py scripts/install.py --project-dir "C:/Path/Project"
py scripts/install.py --dry-run --project "C:/Path/Project/Project.uproject"
py scripts/install.py --force --project "C:/Path/Project/Project.uproject"
```

Without an explicit path, the installer checks the current directory, its parents, and then performs a depth-limited search below the current directory. It never scans an entire system drive. If multiple projects are found in an interactive terminal, it asks which one to use.

Existing destination files are skipped. `--force` creates timestamped sibling backups before replacement.

## Unreal plugins

The installer reports whether `PythonScriptPlugin` and `EditorScriptingUtilities` are enabled. Enable them manually in Unreal Editor and restart the editor, or explicitly permit the installer to update the project descriptor:

```powershell
py scripts/install.py --project "C:/Path/Project/Project.uproject" --enable-plugins
```

`--enable-plugins` creates a timestamped `.uproject` backup first and changes only the required entries in the `Plugins` array.

## Install only the Codex skill

After this repository is published, the standard `$skill-installer` can install only the portable skill:

```text
Use $skill-installer to install from https://github.com/OWNER/unreal-codex-harness/tree/main/.agents/skills/unreal-game-builder
```

That method does not install the Unreal Python harness. Use `scripts/install.py` for the complete integration.

## First run

1. Install the harness and skill.
2. Enable the required Unreal plugins.
3. Open or restart the Unreal project.
4. Open **Window → Developer Tools → Output Log** and confirm:

   ```text
   [AI WATCHER] Watcher started
   ```

5. Open the Unreal project directory in Codex and try:

   ```text
   Use $unreal-game-builder to place three instances of an existing Blueprint actor in a row and save the current level.
   ```

The watcher deliberately treats the existing `actions.json` as already seen at startup. Codex must write a new complete document before the first execution.

## Supported actions

- `content.create_folder`
- `blueprint.create`
- `blueprint.edit`
- `level.spawn_actor`
- `project.save`

Blueprint editing supports adding components, setting component properties and transforms, and setting class-default properties. The harness does not support `level.inspect`, deletion, Blueprint replacement, variables, Event Graph nodes, functions, arbitrary Python, or shell commands. See the installed `references/actions-schema.md` for exact JSON shapes.

## Validate an installation

```powershell
py scripts/validate_install.py "C:/Path/Project"
```

Validation checks required files, JSON, Python syntax, skill frontmatter, schema/handler agreement, forbidden source-machine paths, and required Unreal plugins. It does not start Unreal Editor or modify the project.

## Updating

```powershell
git pull
py scripts/install.py --project "C:/Path/Project/Project.uproject" --force
py scripts/validate_install.py "C:/Path/Project"
```

Review the timestamped backups before removing them.

## Troubleshooting

- No `[AI WATCHER] Watcher started`: confirm both plugins are enabled, restart Unreal Editor, and inspect the Output Log for Python errors.
- `result.json` does not change: ensure Unreal Editor is open, `init_unreal.py` started, and `actions.json` is valid JSON.
- Multiple projects found: pass the exact `.uproject` with `--project`.
- Existing files skipped: review them, then rerun with `--force` if replacement is intended.
- Validation reports missing plugins: enable them manually or reinstall with `--enable-plugins`.

## Safe removal

Close Unreal Editor. Remove only these installed paths from the target project after reviewing local modifications:

```text
Content/Python/execute_actions.py
Content/Python/init_unreal.py
Content/Python/actions.json
.agents/skills/unreal-game-builder/
```

`Content/Python/result.json` is runtime output and can be removed separately if no longer needed. Do not delete the surrounding `Content`, `Python`, or `.agents` directories when they contain unrelated files. Plugin entries in `.uproject` are not removed automatically.

## License

MIT. See [LICENSE](LICENSE).
