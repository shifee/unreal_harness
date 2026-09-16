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


class ExecutorContractTests(unittest.TestCase):
    def run_document(self, document):
        with tempfile.TemporaryDirectory(prefix="unreal-codex-executor-") as directory:
            root = Path(directory)
            shutil.copy2(EXECUTOR, root / "execute_actions.py")
            (root / "actions.json").write_text(json.dumps(document), encoding="utf-8")
            fake_unreal = types.ModuleType("unreal")
            fake_unreal.log = lambda message: None
            fake_unreal.log_error = lambda message: None
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


if __name__ == "__main__":
    unittest.main()
