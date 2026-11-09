"""Media library: folders are registered where they are, never copied."""
import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from corpse.functions.analysis import library as index
from corpse.functions.analysis.library import Library


def tree(folder):
    return sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*"))


def write_png(path, w=64, h=32):
    cv2.imwrite(str(path), np.full((h, w, 3), 120, np.uint8))


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lib = Library(self.root / "db" / "library.sqlite")
        self.legacy = {k: self.root / "legacy" / k for k in index.KINDS}
        self._saved = dict(index.LEGACY_DIRS)
        index.LEGACY_DIRS.update(self.legacy)
        self.photos = self.root / "elsewhere" / "campaign"
        self.photos.mkdir(parents=True)
        write_png(self.photos / "a.png")
        write_png(self.photos / "b.png", 200, 100)

    def tearDown(self):
        index.LEGACY_DIRS.update(self._saved)
        self.lib.close()
        self.tmp.cleanup()

    def test_add_source_does_not_copy_or_touch_anything(self):
        before = tree(self.photos)
        src = self.lib.add_source("photo", self.photos)
        self.assertEqual(src.path, self.photos.resolve())
        self.assertEqual(tree(self.photos), before)
        self.assertEqual(tree(self.root / "legacy"), [])              # nothing was copied into the app folders
        self.assertEqual([s.name for s in self.lib.sources("photo")], ["campaign"])

    def test_same_folder_twice_is_one_entry_and_same_name_gets_a_suffix(self):
        a = self.lib.add_source("photo", self.photos)
        self.assertEqual(self.lib.add_source("photo", self.photos).id, a.id)
        other = self.root / "other" / "campaign"
        other.mkdir(parents=True)
        b = self.lib.add_source("photo", other)
        self.assertEqual((a.name, b.name), ("campaign", "campaign (2)"))

    def test_remove_forgets_the_folder_but_keeps_the_files(self):
        src = self.lib.add_source("photo", self.photos)
        self.lib.remove_source(src.id)
        self.assertEqual(self.lib.source("photo", "campaign"), None)
        self.assertEqual(sorted(p.name for p in self.photos.iterdir()), ["a.png", "b.png"])

    def test_folders_already_in_the_app_folder_are_registered_in_place(self):
        old = self.legacy["video"] / "dive1"
        old.mkdir(parents=True)
        src = self.lib.sources("video")[0]
        self.assertEqual((src.name, src.path), ("dive1", old.resolve()))

    def test_a_missing_folder_is_reported_not_dropped(self):
        folder = self.root / "usb"
        folder.mkdir()
        self.lib.add_source("photo", folder)
        folder.rmdir()
        s = self.lib.sources("photo")[0]
        self.assertFalse(s.exists)
        self.assertEqual(self.lib.files(s), [])

    def test_kinds_are_separate(self):
        self.lib.add_source("photo", self.photos)
        self.assertEqual(self.lib.sources("photo_stereo"), [])
        with self.assertRaises(ValueError):
            self.lib.add_source("nope", self.photos)
        with self.assertRaises(FileNotFoundError):
            self.lib.add_source("photo", self.root / "missing")

    def test_files_and_info_are_read_from_the_originals(self):
        src = self.lib.add_source("photo", self.photos)
        files = self.lib.files(src)
        self.assertEqual([f.name for f in files], ["a.png", "b.png"])
        info = self.lib.info(files[1])
        self.assertEqual((info.kind, info.width, info.height, info.size), ("image", 200, 100, files[1].stat().st_size))
        write_png(files[1], 10, 10)                                    # file changed: the cache must notice
        os.utime(files[1], (1, 1))
        self.assertEqual(self.lib.info(files[1]).width, 10)

    def test_thumbnail_is_made_in_memory_and_is_small(self):
        src = self.lib.add_source("photo", self.photos)
        big = self.photos / "big.png"
        write_png(big, 800, 400)
        before = tree(self.photos)
        data = self.lib.thumbnail(big, 140)
        self.assertEqual(tree(self.photos), before)                    # no thumbnail file anywhere
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(max(img.shape[:2]), 140)
        self.assertIs(self.lib.thumbnail(big, 140), data)               # served from the RAM cache

    def test_video_info_and_thumbnail(self):
        path = self.root / "clip.avi"
        w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
        for i in range(20):
            w.write(np.full((48, 64, 3), i * 10, np.uint8))
        w.release()
        info = self.lib.info(path)
        self.assertEqual((info.kind, info.width, info.height, info.frames), ("video", 64, 48, 20))
        self.assertAlmostEqual(info.duration, 2.0, places=1)
        self.assertTrue(self.lib.thumbnail(path).startswith(b"\xff\xd8"))

    def test_unreadable_files_raise_clearly(self):
        bad = self.root / "bad.png"
        bad.write_bytes(b"not an image")
        with self.assertRaises(ValueError):
            self.lib.info(bad)

    def test_index_survives_reopening(self):
        self.lib.add_source("photo", self.photos)
        self.lib.close()
        self.lib = Library(self.root / "db" / "library.sqlite")
        self.assertEqual([s.name for s in self.lib.sources("photo")], ["campaign"])


if __name__ == "__main__":
    unittest.main()
