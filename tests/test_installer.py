import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("harness_installer", ROOT / "scripts/install.py")
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerTests(unittest.TestCase):
    def write_project(self, root, association):
        path = root / "Test.uproject"
        path.write_text(
            json.dumps({"FileVersion": 3, "EngineAssociation": association, "Plugins": []}),
            encoding="utf-8",
        )
        return path

    def test_accepts_ue58_project(self):
        with tempfile.TemporaryDirectory(prefix="unreal-codex-install-") as directory:
            path, data = INSTALLER.validate_project_file(
                self.write_project(Path(directory), "5.8")
            )
            self.assertEqual(path.name, "Test.uproject")
            self.assertEqual(data["EngineAssociation"], "5.8")

    def test_rejects_known_older_engine(self):
        with tempfile.TemporaryDirectory(prefix="unreal-codex-install-") as directory:
            with self.assertRaisesRegex(ValueError, "targets Unreal Engine 5.8"):
                INSTALLER.validate_project_file(
                    self.write_project(Path(directory), "5.7")
                )


if __name__ == "__main__":
    unittest.main()
