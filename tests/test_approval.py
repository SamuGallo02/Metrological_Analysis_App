import tempfile
import unittest
from datetime import date
from pathlib import Path

from common.errors import AppError
from tests.util import upload_as_user
from server.params import AREA_DIRS
from server.storage import Storage

DAY = date(2026, 10, 22)


class ApprovalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Storage(Path(self._tmp.name))
        self.species_dir = self.store.root / AREA_DIRS["species"] / "Pinna nobilis"

    def _upload(self, username, rel, data=b"x"):
        upload_as_user(self.store, rel, username=username, data=data)

    def test_mono_is_approved(self):
        self._upload("francy", "Pinna nobilis/b.jpg", b"B")
        self._upload("francy", "Pinna nobilis/a.jpg", b"A")
        name, count = self.store.approve_species("francy", "Pinna nobilis", DAY)
        self.assertEqual((name, count), ("Pinna nobilis_francy_2026-10-22", 2))
        folder = self.species_dir / name
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["IMG_0001.jpg", "IMG_0002.jpg"])
        self.assertEqual((folder / "IMG_0001.jpg").read_bytes(), b"A")
        with self.assertRaises(AppError):                              # la quarantena è stata svuotata
            self.store.pending_species_dir("francy", "Pinna nobilis")

    def test_stereo_is_approved(self):
        for side in ("lx", "rx"):
            self._upload("francy", f"Pinna nobilis/{side}/x.jpg", side.encode())
        name, count = self.store.approve_species("francy", "Pinna nobilis", DAY)
        self.assertEqual(count, 2)
        self.assertEqual((self.species_dir / name / "lx/IMG_0001.jpg").read_bytes(), b"lx")
        self.assertEqual((self.species_dir / name / "rx/IMG_0001.jpg").read_bytes(), b"rx")

    def test_same_day_gets_a_counter(self):
        self._upload("francy", "Pinna nobilis/a.jpg")
        first, _ = self.store.approve_species("francy", "Pinna nobilis", DAY)
        self._upload("francy", "Pinna nobilis/a.jpg")
        second, _ = self.store.approve_species("francy", "Pinna nobilis", DAY)
        self.assertEqual(first, "Pinna nobilis_francy_2026-10-22")
        self.assertEqual(second, "Pinna nobilis_francy_2026-10-22_2")
        self.assertEqual(sorted(p.name for p in self.species_dir.iterdir()), [first, second])   # niente residui

    def test_two_users_do_not_clash(self):
        self._upload("francy", "Pinna nobilis/a.jpg")
        self._upload("ugo", "Pinna nobilis/a.jpg")
        self.store.approve_species("francy", "Pinna nobilis", DAY)
        self.store.approve_species("ugo", "Pinna nobilis", DAY)
        self.assertEqual(sorted(p.name for p in self.species_dir.iterdir()),
                         ["Pinna nobilis_francy_2026-10-22", "Pinna nobilis_ugo_2026-10-22"])

    def test_incomplete_folder_is_not_approved(self):
        self._upload("francy", "Pinna nobilis/lx/a.jpg")
        self._upload("francy", "Pinna nobilis/rx/b.jpg")                # i nomi non combaciano
        with self.assertRaises(AppError):
            self.store.approve_species("francy", "Pinna nobilis", DAY)
        self.store.pending_species_dir("francy", "Pinna nobilis")        # la quarantena è ancora lì
        self.assertFalse(self.species_dir.exists())                      # e non è stato creato nulla


if __name__ == "__main__":
    unittest.main()