import tempfile
import unittest
from pathlib import Path

from common.errors import AppError
from tests.util import upload_as_user
from server.storage import Storage


class QuarantineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Storage(Path(self._tmp.name))

    def _upload_as_user(self, area, rel):
        """Simula l'upload di un utente normale e crea davvero il file in quarantena."""
        return upload_as_user(self.store, rel, area=area)[1]

    def test_models_pending_is_hidden_from_users(self):
        eff = self._upload_as_user("models", "Pinna nobilis/m.pt")
        with self.assertRaises(AppError):
            self.store.resolve("models", eff, False, "altro")
        self.store.resolve("models", eff, True, "admin")          # l'admin può
        self.assertNotIn("_pending", [e["name"] for e in self.store.list_dir("models", "", False, "altro")["entries"]])

    def test_species_pending_is_hidden_from_users(self):
        eff = self._upload_as_user("species", "Pinna nobilis/a.jpg")
        with self.assertRaises(AppError):
            self.store.resolve("species", eff, False, "altro")
        self.store.resolve("species", eff, True, "admin")
        self.assertNotIn("_pending", [e["name"] for e in self.store.list_dir("species", "", False, "altro")["entries"]])
        self.assertIn("_pending", [e["name"] for e in self.store.list_dir("species", "", True, "admin")["entries"]])
    
    def test_users_cannot_create_folders_in_quarantine_areas(self):
        for area in ("models", "species"):
            with self.subTest(area=area):
                with self.assertRaises(AppError):
                    self.store.mkdir(area, "Pinna nobilis", False, "francy")

    def test_quarantine_root_cannot_be_deleted(self):
        for area in ("models", "species"):
            with self.subTest(area=area):
                with self.assertRaises(AppError):
                    self.store.delete(area, "_pending")

    def test_pending_species_dir(self):
        self._upload_as_user("species", "Pinna nobilis/a.jpg")
        folder = self.store.pending_species_dir("francy", "Pinna nobilis")
        self.assertTrue(folder.is_dir())
        with self.assertRaises(AppError):
            self.store.pending_species_dir("francy", "Epinephelus marginatus")   # mai caricata
        with self.assertRaises(AppError):
            self.store.pending_species_dir("francy", "../francy")                # nome non valido
        with self.assertRaises(AppError):
            self.store.pending_species_dir("altro", "Pinna nobilis")             # le foto sono di un altro utente