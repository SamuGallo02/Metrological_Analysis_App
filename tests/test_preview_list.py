import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpse.functions.users.preview import list_preview
from tests.util import FakeServerClient


class ListPreviewTest(unittest.TestCase):
    def test_lists_the_first_images_and_counts_the_others(self):
        folder = {f"{n:02d}.jpg": b"x" for n in range(5)}
        folder["notes.txt"] = b"text"                                     # not an image: it does not count
        info = list_preview(FakeServerClient({"Pinna nobilis": folder}), "photos", "Pinna nobilis", limit=3)
        self.assertEqual(info["images"], [f"Pinna nobilis/0{n}.jpg" for n in range(3)])
        self.assertEqual((info["total"], info["more"]), (5, 2))

    def test_stereo_photos_are_found_in_both_sides(self):
        tree = {"Pinna nobilis": {"lx": {"a.jpg": b"x"}, "rx": {"a.jpg": b"x"}}}
        info = list_preview(FakeServerClient(tree), "photos", "Pinna nobilis")
        self.assertEqual(info["images"], ["Pinna nobilis/lx/a.jpg", "Pinna nobilis/rx/a.jpg"])
        self.assertEqual(info["more"], 0)

    def test_an_empty_folder_has_no_images(self):
        info = list_preview(FakeServerClient({"vuota": {}}), "photos", "vuota")
        self.assertEqual((info["images"], info["total"], info["more"]), ([], 0, 0))


if __name__ == "__main__":
    unittest.main()