#!/usr/bin/env python3
"""Install the Unreal Codex harness into an existing Unreal Engine project."""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = REPO_ROOT / "templates" / "unreal-project"
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / "unreal-game-builder"
REQUIRED_PLUGINS = ("PythonScriptPlugin", "EditorScriptingUtilities")
MAX_SEARCH_DEPTH = 4
SKIP_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "Binaries",
    "DerivedDataCache",
    "Intermediate",
    "node_modules",
    "Saved",
    "__pycache__",
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--project", type=Path, help="Path to a .uproject file")
    group.add_argument("--project-dir", type=Path, help="Directory containing a .uproject")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--force", action="store_true", help="Back up and replace conflicts")
    parser.add_argument(
        "--enable-plugins",
        action="store_true",
        help="Back up the .uproject and enable required editor plugins",
    )
    return parser.parse_args(argv)


def direct_projects(directory):
    if not directory.is_dir():
        return []
    return sorted(path.resolve() for path in directory.glob("*.uproject") if path.is_file())


def validate_project_file(path):
    path = path.expanduser().resolve()
    if path.suffix.lower() != ".uproject":
        raise ValueError("Project path must end with .uproject: {}".format(path))
    if not path.is_file():
        raise ValueError("Project file does not exist: {}".format(path))
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Invalid .uproject JSON: {}".format(error))
    if not isinstance(data, dict):
        raise ValueError("The .uproject root must be a JSON object")
    return path, data


def recursive_projects(start, max_depth=MAX_SEARCH_DEPTH):
    start = start.resolve()
    found = []
    stack = [(start, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            entries = list(directory.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            if entry.is_file() and entry.suffix.lower() == ".uproject":
                found.append(entry.resolve())
        if depth >= max_depth:
            continue
        for entry in entries:
            if entry.is_dir() and entry.name not in SKIP_DIRS and not entry.is_symlink():
                stack.append((entry, depth + 1))
    return sorted(set(found))


def choose_project(candidates):
    candidates = sorted(set(candidates))
    if not candidates:
        raise ValueError("No Unreal project found. Pass --project PATH_TO_PROJECT.uproject")
    if len(candidates) == 1:
        return candidates[0]
    print("Multiple Unreal projects found:")
    for index, path in enumerate(candidates, 1):
        print("  {}. {}".format(index, path))
    if not sys.stdin.isatty():
        raise ValueError("Multiple projects found in non-interactive mode; pass --project")
    while True:
        answer = input("Choose a project number: ").strip()
        try:
            selected = int(answer)
        except ValueError:
            selected = 0
        if 1 <= selected <= len(candidates):
            return candidates[selected - 1]
        print("Enter a number from 1 to {}.".format(len(candidates)))


def find_project(args, cwd):
    if args.project:
        return args.project.expanduser().resolve()
    if args.project_dir:
        candidates = direct_projects(args.project_dir.expanduser().resolve())
        return choose_project(candidates)

    current = cwd.resolve()
    for directory in (current,) + tuple(current.parents):
        candidates = direct_projects(directory)
        if candidates:
            return choose_project(candidates)
    return choose_project(recursive_projects(current))


def backup_path(path):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(path.name + ".bak." + stamp)
    counter = 1
    while candidate.exists():
        candidate = path.with_name(path.name + ".bak.{}.{}".format(stamp, counter))
        counter += 1
    return candidate


def copy_file(source, destination, dry_run, force, report):
    if destination.exists() and not force:
        report["skipped"].append(destination)
        return
    if destination.exists():
        backup = backup_path(destination)
        if not dry_run:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(destination), str(backup))
        report["backups"].append(backup)
        report["replaced"].append(destination)
    else:
        report["created"].append(destination)
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(destination))


def plugin_status(project_data):
    entries = project_data.get("Plugins", [])
    enabled = {
        entry.get("Name")
        for entry in entries
        if isinstance(entry, dict) and entry.get("Enabled") is True
    }
    return {name: name in enabled for name in REQUIRED_PLUGINS}


def enable_plugins(project_file, project_data, dry_run, report):
    plugins = project_data.get("Plugins")
    if not isinstance(plugins, list):
        plugins = []
        project_data["Plugins"] = plugins
    by_name = {
        entry.get("Name"): entry
        for entry in plugins
        if isinstance(entry, dict) and isinstance(entry.get("Name"), str)
    }
    changed = False
    for name in REQUIRED_PLUGINS:
        if name in by_name:
            if by_name[name].get("Enabled") is not True:
                by_name[name]["Enabled"] = True
                changed = True
        else:
            plugins.append({"Name": name, "Enabled": True})
            changed = True
    if not changed:
        return
    backup = backup_path(project_file)
    report["backups"].append(backup)
    report["plugins_enabled"].extend(REQUIRED_PLUGINS)
    if not dry_run:
        shutil.copy2(str(project_file), str(backup))
        with project_file.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(project_data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def print_report(project_file, dry_run, report, status):
    print("Project: {}".format(project_file))
    print("Mode: {}".format("dry-run" if dry_run else "install"))
    for key, label in (
        ("created", "Created"),
        ("replaced", "Replaced"),
        ("skipped", "Skipped"),
        ("backups", "Backups"),
    ):
        print("{} ({}):".format(label, len(report[key])))
        for path in report[key]:
            print("  - {}".format(path))
    if report["plugins_enabled"]:
        print("Enabled plugins: {}".format(", ".join(REQUIRED_PLUGINS)))
    missing = [name for name, enabled in status.items() if not enabled]
    if missing:
        print("Required plugins not enabled: {}".format(", ".join(missing)))
        print("Enable them in Unreal Editor or rerun with --enable-plugins.")
    else:
        print("Required plugins enabled: {}".format(", ".join(REQUIRED_PLUGINS)))


def install(args):
    project_file, project_data = validate_project_file(find_project(args, Path.cwd()))
    project_root = project_file.parent
    report = {
        "created": [],
        "replaced": [],
        "skipped": [],
        "backups": [],
        "plugins_enabled": [],
    }
    mappings = (
        (TEMPLATE_ROOT / "Content/Python/execute_actions.py", project_root / "Content/Python/execute_actions.py"),
        (TEMPLATE_ROOT / "Content/Python/init_unreal.py", project_root / "Content/Python/init_unreal.py"),
        (TEMPLATE_ROOT / "Content/Python/actions.example.json", project_root / "Content/Python/actions.json"),
        (SKILL_ROOT / "SKILL.md", project_root / ".agents/skills/unreal-game-builder/SKILL.md"),
        (SKILL_ROOT / "agents/openai.yaml", project_root / ".agents/skills/unreal-game-builder/agents/openai.yaml"),
        (SKILL_ROOT / "references/actions-schema.md", project_root / ".agents/skills/unreal-game-builder/references/actions-schema.md"),
    )
    for source, destination in mappings:
        if not source.is_file():
            raise ValueError("Distribution file missing: {}".format(source))
        copy_file(source, destination, args.dry_run, args.force, report)

    if args.enable_plugins:
        enable_plugins(project_file, project_data, args.dry_run, report)
    status = plugin_status(project_data)
    print_report(project_file, args.dry_run, report, status)

    if not args.dry_run:
        print("Install files verified: {}".format(all(path.is_file() for _, path in mappings)))
    return 0


def main():
    try:
        return install(parse_args())
    except (ValueError, OSError) as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
