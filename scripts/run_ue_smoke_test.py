#!/usr/bin/env python3
"""Run the installed harness end to end in an Unreal Engine 5.8 test project."""

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES_FIXTURE = REPO_ROOT / "tests/fixtures/capabilities-v0.1.json"
DEFAULT_WINDOWS_EDITOR = Path(
    "C:/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe"
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path, help="Path to the test .uproject")
    parser.add_argument("--editor-cmd", type=Path, help="Path to UnrealEditor-Cmd executable")
    parser.add_argument("--namespace", help="Unique asset folder name under /Game/CodexHarnessSmoke")
    return parser.parse_args(argv)


def resolve_editor(explicit):
    candidates = []
    if explicit:
        candidates.append(explicit.expanduser())
    discovered = shutil.which("UnrealEditor-Cmd")
    if discovered:
        candidates.append(Path(discovered))
    candidates.append(DEFAULT_WINDOWS_EDITOR)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError("UnrealEditor-Cmd was not found; pass --editor-cmd")


def smoke_document(namespace):
    folder = "/Game/CodexHarnessSmoke/" + namespace
    material = folder + "/M_Smoke.M_Smoke"
    blueprint = folder + "/BP_Smoke.BP_Smoke"
    actor_label = "CodexHarnessSmoke_" + namespace
    return {
        "format_version": "1.0",
        "commands": [
            {"id": "capabilities", "action": "system.capabilities", "arguments": {}},
            {"id": "folder", "action": "content.create_folder", "arguments": {"path": folder}},
            {
                "id": "material",
                "action": "material.create",
                "depends_on": ["folder"],
                "arguments": {
                    "folder": folder,
                    "name": "M_Smoke",
                    "base_color": [0.12, 0.14, 0.17, 1.0],
                    "metallic": 1.0,
                    "roughness": 0.35,
                },
            },
            {
                "id": "blueprint",
                "action": "blueprint.create",
                "depends_on": ["folder"],
                "arguments": {
                    "folder": folder,
                    "name": "BP_Smoke",
                    "parent_class": "/Script/Engine.Actor",
                },
            },
            {
                "id": "components",
                "action": "blueprint.edit",
                "depends_on": ["material", "blueprint"],
                "arguments": {
                    "blueprint": blueprint,
                    "operations": [
                        {
                            "operation": "add_component",
                            "component_type": "/Script/Engine.StaticMeshComponent",
                            "component_name": "SmokeMesh",
                            "attach_to": "DefaultSceneRoot",
                        },
                        {
                            "operation": "set_component_property",
                            "component_name": "SmokeMesh",
                            "property": "static_mesh",
                            "value": "/Engine/BasicShapes/Sphere.Sphere",
                        },
                        {
                            "operation": "set_component_material",
                            "component_name": "SmokeMesh",
                            "slot": 0,
                            "material": material,
                        },
                    ],
                    "compile": True,
                    "save": False,
                },
            },
            {
                "id": "begin_play",
                "action": "blueprint.graph.add_node",
                "depends_on": ["blueprint"],
                "arguments": {
                    "blueprint": blueprint,
                    "graph": "EventGraph",
                    "node_id": "begin_play",
                    "node": {
                        "kind": "event",
                        "owner_class": "/Script/Engine.Actor",
                        "function": "ReceiveBeginPlay",
                    },
                    "position": [0, 0],
                },
            },
            {
                "id": "print",
                "action": "blueprint.graph.add_node",
                "depends_on": ["blueprint"],
                "arguments": {
                    "blueprint": blueprint,
                    "graph": "EventGraph",
                    "node_id": "print",
                    "node": {
                        "kind": "function_call",
                        "owner_class": "/Script/Engine.KismetSystemLibrary",
                        "function": "PrintString",
                    },
                    "position": [350, 0],
                },
            },
            {
                "id": "message",
                "action": "blueprint.graph.set_pin_value",
                "depends_on": ["print"],
                "arguments": {
                    "blueprint": blueprint,
                    "graph": "EventGraph",
                    "node": "print",
                    "pin": "InString",
                    "value": "Unreal Codex Harness smoke test",
                },
            },
            {
                "id": "wire",
                "action": "blueprint.graph.connect",
                "depends_on": ["begin_play", "print"],
                "arguments": {
                    "blueprint": blueprint,
                    "graph": "EventGraph",
                    "from": {"node": "begin_play", "pin": "then"},
                    "to": {"node": "print", "pin": "execute"},
                },
            },
            {
                "id": "compile",
                "action": "blueprint.compile",
                "depends_on": ["components", "message", "wire"],
                "arguments": {"blueprint": blueprint, "save": False},
            },
            {
                "id": "spawn",
                "action": "level.spawn_actor",
                "depends_on": ["compile"],
                "arguments": {
                    "level": "current",
                    "class": blueprint + "_C",
                    "actor_label": actor_label,
                    "transform": {"location": [0, 0, 100]},
                },
            },
            {
                "id": "inspect_actor",
                "action": "level.inspect",
                "depends_on": ["spawn"],
                "arguments": {"query": actor_label, "limit": 10},
            },
            {
                "id": "save_assets",
                "action": "project.save",
                "depends_on": ["compile"],
                "arguments": {"save_level": False, "save_assets": True},
            },
        ],
    }


def validate_result(result):
    if result.get("success") is not True:
        raise AssertionError("Harness result failed: {}".format(result.get("errors")))
    commands = {item["id"]: item for item in result.get("commands", [])}
    expected_ids = {
        "capabilities", "folder", "material", "blueprint", "components",
        "begin_play", "print", "message", "wire", "compile", "spawn",
        "inspect_actor", "save_assets",
    }
    if set(commands) != expected_ids:
        raise AssertionError("Unexpected command results: {}".format(sorted(commands)))
    fixture = json.loads(CAPABILITIES_FIXTURE.read_text(encoding="utf-8"))
    capabilities = commands["capabilities"]["data"]
    if capabilities.get("harness_version") != fixture["harness_version"]:
        raise AssertionError("Harness version differs from capability fixture")
    if capabilities.get("actions") != fixture["actions"]:
        raise AssertionError("Action catalog differs from capability fixture")
    node_kinds = capabilities.get("graph_bridge", {}).get("node_kinds")
    if node_kinds != fixture["graph_node_kinds"]:
        raise AssertionError("Graph node kinds differ from capability fixture")
    if commands["inspect_actor"]["data"].get("total") != 1:
        raise AssertionError("Spawned smoke actor was not found uniquely")
    if not result.get("changed_objects"):
        raise AssertionError("Mutation audit did not report changed_objects")
    for command in result["commands"]:
        if "changed_objects" not in command:
            raise AssertionError("Command lacks changed_objects: " + command["id"])


def main(argv=None):
    args = parse_args(argv)
    project = args.project.expanduser().resolve()
    if not project.is_file() or project.suffix.lower() != ".uproject":
        raise ValueError("Invalid .uproject path: {}".format(project))
    editor = resolve_editor(args.editor_cmd)
    python_dir = project.parent / "Content/Python"
    executor = python_dir / "execute_actions.py"
    actions = python_dir / "actions.json"
    result_path = python_dir / "result.json"
    if not executor.is_file():
        raise ValueError("Harness is not installed: {}".format(executor))

    namespace = args.namespace or "Run_{}_{}".format(
        datetime.now().strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:6]
    )
    backups = {}
    for path in (actions, result_path):
        backups[path] = path.read_bytes() if path.exists() else None
    try:
        actions.write_text(
            json.dumps(smoke_document(namespace), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                str(editor),
                str(project),
                "-run=pythonscript",
                "-script={}".format(executor),
                "-unattended",
                "-nop4",
                "-nosplash",
                "-NullRHI",
                "-stdout",
            ],
            cwd=str(project.parent),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if not result_path.is_file():
            raise AssertionError("Unreal did not write result.json\n" + completed.stdout[-8000:])
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        validate_result(result)
        if completed.returncode != 0:
            raise AssertionError(
                "Unreal commandlet returned {} despite a successful result\n{}".format(
                    completed.returncode, completed.stdout[-8000:]
                )
            )
        print("PASS: Unreal Engine smoke test")
        print("Project: {}".format(project))
        print("Namespace: /Game/CodexHarnessSmoke/{}".format(namespace))
        print("Changed objects: {}".format(len(result["changed_objects"])))
        return 0
    finally:
        for path, content in backups.items():
            if content is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(content)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("FAIL: {}".format(error), file=sys.stderr)
        sys.exit(1)
