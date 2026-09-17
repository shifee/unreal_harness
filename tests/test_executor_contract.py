import json
import runpy
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTOR = ROOT / "templates/unreal-project/Content/Python/execute_actions.py"
ACTION_FIXTURE = ROOT / "tests/fixtures/actions-v0.1.json"


class ExecutorContractTests(unittest.TestCase):
    def run_document(self, document, configure_unreal=None):
        with tempfile.TemporaryDirectory(prefix="unreal-codex-executor-") as directory:
            root = Path(directory)
            shutil.copy2(EXECUTOR, root / "execute_actions.py")
            (root / "actions.json").write_text(json.dumps(document), encoding="utf-8")
            fake_unreal = types.ModuleType("unreal")
            fake_unreal.log = lambda message: None
            fake_unreal.log_error = lambda message: None
            if configure_unreal:
                configure_unreal(fake_unreal)
            previous = sys.modules.get("unreal")
            sys.modules["unreal"] = fake_unreal
            try:
                runpy.run_path(str(root / "execute_actions.py"), run_name="__main__")
            finally:
                if previous is None:
                    del sys.modules["unreal"]
                else:
                    sys.modules["unreal"] = previous
            return json.loads((root / "result.json").read_text(encoding="utf-8"))

    def test_dry_run_validates_without_unreal_calls(self):
        result = self.run_document(
            {
                "format_version": "1.0",
                "dry_run": True,
                "commands": [
                    {
                        "id": "inspect",
                        "action": "level.inspect",
                        "arguments": {"limit": 10},
                    },
                    {
                        "id": "save",
                        "action": "project.save",
                        "depends_on": ["inspect"],
                        "arguments": {},
                    },
                ],
            }
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual([item["id"] for item in result["plan"]], ["inspect", "save"])
        self.assertFalse(result["plan"][0]["mutating"])
        self.assertEqual(result["changed_objects"], [])

    def test_dry_run_structure_is_deterministic(self):
        document = {
            "format_version": "1.0",
            "dry_run": True,
            "commands": [
                {"id": "capabilities", "action": "system.capabilities", "arguments": {}},
                {"id": "inspect", "action": "level.inspect", "arguments": {"limit": 10}},
            ],
        }
        first = self.run_document(document)
        second = self.run_document(document)
        for result in (first, second):
            result.pop("run_id")
            result.pop("started_at")
            result.pop("finished_at")
        self.assertEqual(first, second)

    def test_duplicate_ids_fail_before_execution(self):
        result = self.run_document(
            {
                "format_version": "1.0",
                "commands": [
                    {"id": "same", "action": "level.inspect", "arguments": {}},
                    {"id": "same", "action": "level.inspect", "arguments": {}},
                ],
            }
        )
        self.assertFalse(result["success"])
        self.assertIn("Duplicate command id", result["errors"][0]["message"])
        self.assertEqual(result["errors"][0]["code"], "duplicate_command_id")
        self.assertEqual(result["changed_objects"], [])

    def test_forward_dependency_fails_before_execution(self):
        result = self.run_document(
            {
                "format_version": "1.0",
                "commands": [
                    {
                        "id": "first",
                        "action": "project.save",
                        "depends_on": ["later"],
                        "arguments": {},
                    },
                    {"id": "later", "action": "level.inspect", "arguments": {}},
                ],
            }
        )
        self.assertFalse(result["success"])
        self.assertIn("Dependencies must refer to earlier commands", result["errors"][0]["message"])
        self.assertEqual(result["errors"][0]["code"], "invalid_dependencies")

    def test_all_documented_actions_have_a_dry_run_fixture(self):
        actions = json.loads(ACTION_FIXTURE.read_text(encoding="utf-8"))
        document = {
            "format_version": "1.0",
            "dry_run": True,
            "commands": [
                {"id": "fixture_{}".format(index), "action": action, "arguments": arguments}
                for index, (action, arguments) in enumerate(actions.items())
            ],
        }
        result = self.run_document(document)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["plan"]), 22)
        self.assertEqual({item["action"] for item in result["plan"]}, set(actions))

    def test_content_list_normalizes_unreal_array_values_to_strings(self):
        class UnrealPath:
            def __str__(self):
                return "/Game/Test/BP_Test.BP_Test"

        def configure(fake_unreal):
            fake_unreal.EditorAssetLibrary = types.SimpleNamespace(
                list_assets=lambda path, recursive, include_folder: [UnrealPath()]
            )

        result = self.run_document(
            {
                "format_version": "1.0",
                "commands": [
                    {
                        "id": "list",
                        "action": "content.list",
                        "arguments": {"path": "/Game/Test", "limit": 10},
                    }
                ],
            },
            configure,
        )
        self.assertTrue(result["success"])
        self.assertEqual(
            result["commands"][0]["data"]["assets"],
            ["/Game/Test/BP_Test.BP_Test"],
        )


if __name__ == "__main__":
    unittest.main()
