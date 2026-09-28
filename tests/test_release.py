"""Έλεγχοι του release χωρίς camera, Internet ή αλλαγή ρυθμίσεων Windows."""
import builtins
import hashlib
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from eyedesk import models
from eyedesk.vision import run_worker


class ModelBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = b"model-test-fixture"
        self.models = {"sample": hashlib.sha256(self.data).hexdigest()}
        self.addCleanup(patch.stopall)
        patch.object(models, "ROOT", self.root).start()
        patch.object(models, "MODELS", self.models).start()
        self.download = patch.object(models, "urlopen").start()

    def install(self, data=None):
        folder = self.root / "models"
        folder.mkdir()
        path = folder / "sample.task"
        path.write_bytes(self.data if data is None else data)
        return path

    def test_frozen_valid_bundle_needs_no_writes_or_network(self):
        path = self.install()
        with patch.object(models.sys, "frozen", True, create=True), \
             patch.object(Path, "mkdir", side_effect=AssertionError("read-only bundle")):
            self.assertEqual(models.ensure_models(), {"sample": str(path)})
        self.download.assert_not_called()

    def test_unicode_folder_loads_validated_bytes_for_native_api(self):
        self.root = self.root / "δοκιμή πακέτου"
        self.root.mkdir()
        with patch.object(models, "ROOT", self.root), patch.object(models.sys, "frozen", True, create=True):
            self.install()
            self.assertEqual(models.load_model_buffers(), {"sample": self.data})
        self.download.assert_not_called()

    def test_frozen_missing_bundle_does_not_create_directory_or_download(self):
        with patch.object(models.sys, "frozen", True, create=True):
            with self.assertRaisesRegex(RuntimeError, "Κατέβασε ξανά"):
                models.ensure_models()
        self.assertFalse((self.root / "models").exists())
        self.download.assert_not_called()

    def test_frozen_corrupt_model_is_not_replaced(self):
        path = self.install(b"corrupted")
        with patch.object(models.sys, "frozen", True, create=True):
            with self.assertRaisesRegex(RuntimeError, "αλλοιωθεί"):
                models.ensure_models()
        self.assertEqual(path.read_bytes(), b"corrupted")
        self.download.assert_not_called()

    def test_frozen_unreadable_model_gives_recovery_instruction(self):
        self.install()
        with patch.object(models.sys, "frozen", True, create=True), \
             patch.object(Path, "read_bytes", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(RuntimeError, "Δεν διαβάζεται"):
                models.ensure_models()
        self.download.assert_not_called()

    def test_source_download_still_verifies_before_installing(self):
        self.download.return_value.__enter__.return_value.read.return_value = self.data
        with patch.object(models.sys, "frozen", False, create=True):
            paths = models.ensure_models(report=lambda _text: None)
        self.assertEqual(Path(paths["sample"]).read_bytes(), self.data)
        self.assertFalse((self.root / "models" / "sample.part").exists())
        self.download.assert_called_once()

    def test_source_bad_download_keeps_existing_file(self):
        path = self.install(b"previous-bad-file")
        self.download.return_value.__enter__.return_value.read.return_value = b"bad-download"
        with patch.object(models.sys, "frozen", False, create=True):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                models.ensure_models(report=lambda _text: None)
        self.assertEqual(path.read_bytes(), b"previous-bad-file")


class WorkerImportTests(unittest.TestCase):
    def test_missing_native_dependency_reaches_gui_error_channel(self):
        channel = queue.Queue()
        channel.cancel_join_thread = MagicMock()
        original_import = builtins.__import__

        def missing_cv2(name, *args, **kwargs):
            if name == "cv2":
                raise ImportError("cv2 native DLL missing")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=missing_cv2):
            run_worker(0, channel, MagicMock())
        self.assertEqual(channel.get_nowait(), {"kind": "error", "text": "cv2 native DLL missing"})
        channel.cancel_join_thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
