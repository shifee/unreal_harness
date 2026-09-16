#!/usr/bin/env python3
"""Validate an installed Unreal Codex harness without starting Unreal Editor."""

import argparse
import ast
import json
import py_compile
import re
import sys
import tempfile
from pathlib import Path


REQUIRED_PLUGINS = ("PythonScriptPlugin", "EditorScriptingUtilities")
REQUIRED_FILES = (
    "Content/Python/execute_actions.py",
    "Content/Python/init_unreal.py",
    "Content/Python/actions.json",
    ".agents/skills/unreal-game-builder/SKILL.md",
    ".agents/skills/unreal-game-builder/references/actions-schema.md",
)
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/](?:Users|Storage)[\\/]")


def find_project(root):
    projects = sorted(root.glob("*.uproject"))
    if len(projects) != 1:
        raise ValueError("Expected exactly one .uproject in {}; found {}".format(root, len(projects)))
    return projects[0]


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    result = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip("\"'")
    return result


def action_handlers_from_python(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "ACTION_HANDLERS" for target in targets):
                value = node.value
                if not isinstance(value, ast.Dict):
                    break
                return {
                    key.value
                    for key in value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
    raise ValueError("ACTION_HANDLERS mapping not found")


def validate(root):
    errors = []
    checks = []
    try:
        project_file = find_project(root)
        checks.append("one .uproject found")
    except ValueError as error:
        return [str(error)], checks

    try:
        project_data = json.loads(project_file.read_text(encoding="utf-8-sig"))
        checks.append(".uproject JSON is valid")
    except (OSError, json.JSONDecodeError) as error:
        errors.append("Invalid .uproject JSON: {}".format(error))
        project_data = {}

    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append("Missing file: {}".format(relative))
    if not errors:
        checks.append("all required harness and skill files exist")

    actions_path = root / "Content/Python/actions.json"
    if actions_path.is_file():
        try:
            actions = json.loads(actions_path.read_text(encoding="utf-8-sig"))
            if not isinstance(actions, dict) or not isinstance(actions.get("commands"), list):
                raise ValueError("root object needs a commands array")
            checks.append("actions.json is valid")
        except (OSError, json.JSONDecodeError, ValueError) as error:
            errors.append("Invalid actions.json: {}".format(error))

    scan_files = [root / relative for relative in REQUIRED_FILES if (root / relative).is_file()]
    for path in scan_files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if WINDOWS_ABSOLUTE_PATH.search(text):
            errors.append("Source-machine absolute path found in {}".format(path.relative_to(root)))
    if not any("absolute path" in error for error in errors):
        checks.append("source-machine absolute paths are absent")

    with tempfile.TemporaryDirectory(prefix="unreal-harness-pycompile-") as cache_dir:
        for relative in ("Content/Python/execute_actions.py", "Content/Python/init_unreal.py"):
            path = root / relative
            if path.is_file():
                try:
                    py_compile.compile(
                        str(path),
                        cfile=str(Path(cache_dir) / (path.stem + ".pyc")),
                        doraise=True,
                    )
                except py_compile.PyCompileError as error:
                    errors.append("Python syntax error in {}: {}".format(relative, error))
    if not any("Python syntax error" in error for error in errors):
        checks.append("Python syntax is valid")

    skill_path = root / ".agents/skills/unreal-game-builder/SKILL.md"
    if skill_path.is_file():
        frontmatter = parse_frontmatter(skill_path.read_text(encoding="utf-8-sig"))
        if not frontmatter.get("name") or not frontmatter.get("description"):
            errors.append("SKILL.md frontmatter needs name and description")
        else:
            checks.append("SKILL.md frontmatter is valid")

    executor_path = root / "Content/Python/execute_actions.py"
    schema_path = root / ".agents/skills/unreal-game-builder/references/actions-schema.md"
    if executor_path.is_file() and schema_path.is_file():
        try:
            handler_actions = action_handlers_from_python(executor_path)
            schema_text = schema_path.read_text(encoding="utf-8")
            schema_actions = set(re.findall(r'^## `([^`]+)`$', schema_text, re.MULTILINE))
            if handler_actions != schema_actions:
                errors.append(
                    "Schema/actions mismatch: handlers={}, schema={}".format(
                        sorted(handler_actions), sorted(schema_actions)
                    )
                )
            else:
                checks.append("schema actions match ACTION_HANDLERS")
        except (OSError, SyntaxError, ValueError) as error:
            errors.append("Could not compare schema with ACTION_HANDLERS: {}".format(error))

    enabled = {
        entry.get("Name")
        for entry in project_data.get("Plugins", [])
        if isinstance(entry, dict) and entry.get("Enabled") is True
    }
    missing_plugins = [name for name in REQUIRED_PLUGINS if name not in enabled]
    if missing_plugins:
        errors.append("Required Unreal plugins are not enabled: {}".format(", ".join(missing_plugins)))
    else:
        checks.append("required Unreal plugins are enabled")
    return errors, checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)
    root = args.project_dir.expanduser().resolve()
    errors, checks = validate(root)
    for check in checks:
        print("PASS: " + check)
    for error in errors:
        print("FAIL: " + error)
    print("Validation: {}".format("PASS" if not errors else "FAIL"))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
