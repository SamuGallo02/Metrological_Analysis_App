"""I metadati dei modelli (.json) viaggiano accanto al modello: caricamento e approvazione."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.errors import AppError
from server.params import AREA_DIRS, PENDING
from server.storage import Storage

SPECIES = "Pinna nobilis"


class ModelMetadataFilesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Storage(Path(self._tmp.name))
        self.models = self.store.root / AREA_DIRS["models"]

    def _quarantined(self, *names):
        """Crea dei file direttamente in quarantena (come se un utente li avesse già caricati)."""
        folder = self.models / PENDING / "francy" / SPECIES
        folder.mkdir(parents=True, exist_ok=True)
        for n in names:
            (folder / n).write_bytes(b"x")
        return f"{PENDING}/francy/{SPECIES}"

    def test_a_user_can_upload_metadata_next_to_a_model(self):
        _dest, eff = self.store.check_new_file("models", f"{SPECIES}/m.json", False, "francy", 500)
        self.assertEqual(eff, f"{PENDING}/francy/{SPECIES}/m.json")

    def test_metadata_files_must_be_small(self):
        with self.assertRaises(AppError) as ctx:
            self.store.check_new_file("models", f"{SPECIES}/m.json", False, "francy", 2 << 20)
        self.assertEqual(ctx.exception.status, 413)

    def test_approving_a_model_moves_its_metadata_too(self):
        folder = self._quarantined("m.pt", "m.json")
        self.store.approve_model(f"{folder}/m.pt")
        self.assertTrue((self.models / SPECIES / "m.pt").is_file())
        self.assertTrue((self.models / SPECIES / "m.json").is_file())
        self.assertFalse((self.models / PENDING / "francy" / SPECIES / "m.json").exists())

    def test_metadata_follows_a_renamed_model(self):
        folder = self._quarantined("m.pt", "m.json")
        self.store.approve_model(f"{folder}/m.pt", f"{SPECIES}/new.pt")
        self.assertTrue((self.models / SPECIES / "new.json").is_file())

    def test_a_model_without_metadata_is_approved_as_before(self):
        folder = self._quarantined("m.pt")
        self.store.approve_model(f"{folder}/m.pt")
        self.assertTrue((self.models / SPECIES / "m.pt").is_file())

    def test_nothing_moves_if_the_metadata_destination_is_taken(self):
        folder = self._quarantined("m.pt", "m.json")
        (self.models / SPECIES).mkdir()
        (self.models / SPECIES / "m.json").write_bytes(b"old")
        with self.assertRaises(AppError) as ctx:
            self.store.approve_model(f"{folder}/m.pt")
        self.assertEqual(ctx.exception.status, 409)
        self.assertTrue((self.models / PENDING / "francy" / SPECIES / "m.pt").is_file())   # ancora in quarantena


if __name__ == "__main__":
    unittest.main()