import tempfile
import unittest
from datetime import date
from pathlib import Path

from common.errors import AppError
from tests.util import upload_as_user
from server.storage import Storage

DAY = date(2026, 10, 22)


class ApprovalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Storage(Path(self._tmp.name))
        self.species_dir = self.store.library("photos") / "Pinna nobilis"

    def _upload(self, username, rel, data=b"x", area="photos"):
        upload_as_user(self.store, rel, username=username, area=area, data=data)

    def test_mono_is_approved(self):
        self._upload("francy", "Pinna nobilis/b.jpg", b"B")
        self._upload("francy", "Pinna nobilis/a.jpg", b"A")
        name, count = self.store.approve_media("francy", "Pinna nobilis", "photos", DAY)
        self.assertEqual((name, count), ("Pinna nobilis_francy_2026-10-22", 2))
        folder = self.species_dir / name
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["IMG_0001.jpg", "IMG_0002.jpg"])
        self.assertEqual((folder / "IMG_0001.jpg").read_bytes(), b"A")
        with self.assertRaises(AppError):                              # la quarantena è stata svuotata
            self.store.pending_media_dir("francy", "Pinna nobilis", "photos")

    def test_stereo_is_approved(self):
        for side in ("lx", "rx"):
            self._upload("francy", f"Pinna nobilis/{side}/x.jpg", side.encode(), area="stereo")
        name, count = self.store.approve_media("francy", "Pinna nobilis", "stereo", DAY)
        self.assertEqual(count, 2)
        folder = self.store.library("stereo") / "Pinna nobilis" / name           # stereo photos have their own area
        self.assertEqual((folder / "lx/IMG_0001.jpg").read_bytes(), b"lx")
        self.assertEqual((folder / "rx/IMG_0001.jpg").read_bytes(), b"rx")

    def test_labels_travel_with_their_photo(self):
        self._upload("francy", "Pinna nobilis/a.jpg", b"A")
        self._upload("francy", "Pinna nobilis/a.txt", b"0 0.5 0.5 0.2 0.2")
        name, count = self.store.approve_media("francy", "Pinna nobilis", "photos", DAY)
        self.assertEqual(count, 1)                                          # the label is not a photo
        self.assertEqual((self.species_dir / name / "IMG_0001.txt").read_bytes(), b"0 0.5 0.5 0.2 0.2")

    def test_videos_are_approved_in_their_own_area(self):
        self._upload("francy", "Pinna nobilis/dive.mp4", b"V", area="videos")
        name, count = self.store.approve_media("francy", "Pinna nobilis", "video", DAY)
        self.assertEqual(count, 1)
        self.assertEqual((self.store.library("videos") / "Pinna nobilis" / name / "VID_0001.mp4").read_bytes(), b"V")

    def test_same_day_gets_a_counter(self):
        self._upload("francy", "Pinna nobilis/a.jpg")
        first, _ = self.store.approve_media("francy", "Pinna nobilis", "photos", DAY)
        self._upload("francy", "Pinna nobilis/a.jpg")
        second, _ = self.store.approve_media("francy", "Pinna nobilis", "photos", DAY)
        self.assertEqual(first, "Pinna nobilis_francy_2026-10-22")
        self.assertEqual(second, "Pinna nobilis_francy_2026-10-22_2")
        self.assertEqual(sorted(p.name for p in self.species_dir.iterdir()), [first, second])   # niente residui

    def test_two_users_do_not_clash(self):
        self._upload("francy", "Pinna nobilis/a.jpg")
        self._upload("ugo", "Pinna nobilis/a.jpg")
        self.store.approve_media("francy", "Pinna nobilis", "photos", DAY)
        self.store.approve_media("ugo", "Pinna nobilis", "photos", DAY)
        self.assertEqual(sorted(p.name for p in self.species_dir.iterdir()),
                         ["Pinna nobilis_francy_2026-10-22", "Pinna nobilis_ugo_2026-10-22"])

    def test_incomplete_folder_is_not_approved(self):
        self._upload("francy", "Pinna nobilis/lx/a.jpg", area="stereo")
        self._upload("francy", "Pinna nobilis/rx/b.jpg", area="stereo")          # the names do not match
        with self.assertRaises(AppError):
            self.store.approve_media("francy", "Pinna nobilis", "stereo", DAY)
        self.store.pending_media_dir("francy", "Pinna nobilis", "stereo")        # still waiting
        self.assertFalse((self.store.library("stereo") / "Pinna nobilis").exists())                      # e non è stato creato nulla


if __name__ == "__main__":
    unittest.main()