import ast
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def assigned_string(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    raise AssertionError("{} not found in {}".format(name, path))


class VersionAlignmentTests(unittest.TestCase):
    def test_runtime_and_plugin_versions_match_package(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        package_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE).group(1)
        executor_version = assigned_string(
            ROOT / "templates/unreal-project/Content/Python/execute_actions.py",
            "HARNESS_VERSION",
        )
        plugin = json.loads(
            (ROOT / "templates/unreal-project/Plugins/UnrealCodexGraph/UnrealCodexGraph.uplugin").read_text(encoding="utf-8")
        )
        bridge_source = (
            ROOT / "templates/unreal-project/Plugins/UnrealCodexGraph/Source/UnrealCodexGraph/Private/UnrealCodexGraphLibrary.cpp"
        ).read_text(encoding="utf-8")
        bridge_version = re.search(r'bridge_version"\), TEXT\("([^"]+)', bridge_source).group(1)
        capabilities = json.loads(
            (ROOT / "tests/fixtures/capabilities-v0.1.json").read_text(encoding="utf-8")
        )

        self.assertEqual(executor_version, package_version)
        self.assertEqual(plugin["VersionName"], package_version)
        self.assertEqual(bridge_version, package_version)
        self.assertEqual(capabilities["harness_version"], package_version)


if __name__ == "__main__":
    unittest.main()
