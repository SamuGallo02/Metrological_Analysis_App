"""Structure of the photos, stereo photos and videos of a species, with their labels."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.errors import AppError
from server.media_tree import check_media_file, count_media, label_name, move_numbered, validate_media_dir

SP = "Epinephelus marginatus"
PH, ST, VI = "photos", "stereo", "video"


def touch(root: Path, rel: str, data: bytes = b"x") -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)


class TestCheckMediaFile(unittest.TestCase):
    def test_valid_paths(self):
        self.assertEqual(check_media_file(PH, f"{SP}/a.jpg"), (SP, "a.jpg"))
        self.assertEqual(check_media_file(PH, f"{SP}/a.txt"), (SP, "a.txt"))                   # its label
        for side in ("lx", "rx"):
            self.assertEqual(check_media_file(ST, f"{SP}/{side}/1723130400.PNG"), (SP, side, "1723130400.PNG"))
        self.assertEqual(check_media_file(VI, f"{SP}/dive.mp4"), (SP, "dive.mp4"))
        check_media_file(PH, "Genus species subspecies/a.webp")

    def assert_rejected(self, kind, rel, status, key_start):
        with self.assertRaises(AppError) as cm:
            check_media_file(kind, rel)
        self.assertEqual(cm.exception.status, status, rel)
        self.assertTrue(cm.exception.key.startswith(key_start), rel)

    def test_species_name(self):
        for rel in ("", "a.jpg", "epinephelus marginatus/a.jpg", "Epinephelus/a.jpg", "Epinephelus_marginatus/a.jpg"):
            self.assert_rejected(PH, rel, 422, "The first folder")

    def test_wrong_structure(self):
        for rel in (SP, f"{SP}/sub/a.jpg", f"{SP}/lx/a.jpg"):                  # stereo folders do not belong to photos
            self.assert_rejected(PH, rel, 422, "Wrong folder structure")
        for rel in (SP, f"{SP}/a.jpg", f"{SP}/left/a.jpg", f"{SP}/LX/a.jpg", f"{SP}/lx/sub/a.jpg"):
            self.assert_rejected(ST, rel, 422, "Wrong folder structure")

    def test_file_types(self):
        for name in ("a.pt", "noext", "a.mp4"):
            self.assert_rejected(PH, f"{SP}/{name}", 415, "Extension")
        self.assert_rejected(ST, f"{SP}/lx/a.mp4", 415, "Extension")
        self.assert_rejected(VI, f"{SP}/a.jpg", 415, "Extension")

    def test_error_is_translatable(self):
        with self.assertRaises(AppError) as cm:
            check_media_file(ST, f"{SP}/x/y/a.jpg")
        self.assertIn("Pinna nobilis/lx/image.jpg", str(cm.exception))


class TestValidateMediaDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sp = Path(self.tmp.name) / SP

    def tearDown(self):
        self.tmp.cleanup()

    def test_photos(self):
        touch(self.sp, "a.jpg")
        touch(self.sp, "b.jpg")
        touch(self.sp, "a.txt")                                        # a label of a photo of the folder
        self.assertEqual(validate_media_dir(self.sp, PH), [])
        self.assertEqual(count_media(self.sp, PH), 2)                  # labels are not counted

    def test_a_label_needs_its_media(self):
        touch(self.sp, "a.jpg")
        touch(self.sp, "other.txt")
        problems = validate_media_dir(self.sp, PH)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].key.startswith("The label file"))

    def test_stereo_with_matching_pairs(self):
        for side in ("lx", "rx"):
            touch(self.sp, f"{side}/IMG_0001.jpg")
            touch(self.sp, f"{side}/IMG_0002.jpg")
        touch(self.sp, "lx/IMG_0001.txt")
        self.assertEqual(validate_media_dir(self.sp, ST), [])

    def test_stereo_needs_both_sides(self):
        touch(self.sp, "rx/1.jpg")
        problems = validate_media_dir(self.sp, ST)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].key.startswith("The stereo folder"))
        (self.sp / "lx").mkdir()
        self.assertEqual(len(validate_media_dir(self.sp, ST)), 1)
        touch(self.sp, "lx/1.jpg")
        self.assertEqual(validate_media_dir(self.sp, ST), [])

    def test_pairs_must_have_same_names(self):
        touch(self.sp, "lx/1.jpg")
        touch(self.sp, "lx/2.jpg")
        touch(self.sp, "rx/1.jpg")
        touch(self.sp, "rx/3.jpg")
        problems = validate_media_dir(self.sp, ST)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].key.startswith("The lx and rx"))

    def test_the_kind_decides_the_structure(self):
        touch(self.sp, "a.jpg")
        self.assertTrue(validate_media_dir(self.sp, ST))               # loose photos are not a stereo upload
        for side in ("lx", "rx"):
            touch(self.sp, f"{side}/a.jpg")
        self.assertTrue(validate_media_dir(self.sp, PH))               # lx/rx folders are not a photos upload

    def test_videos(self):
        touch(self.sp, "dive.mp4")
        touch(self.sp, "dive.txt")
        self.assertEqual(validate_media_dir(self.sp, VI), [])
        self.assertTrue(validate_media_dir(self.sp, PH))               # a video is not a photo

    def test_empty_or_without_media(self):
        self.sp.mkdir(parents=True)
        self.assertEqual(validate_media_dir(self.sp, PH)[0].params["folder"], SP)
        touch(self.sp, "notes.txt")
        self.assertTrue(validate_media_dir(self.sp, PH))


class TestMoveNumbered(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "src"
        self.dst = Path(self.tmp.name) / "dst"          # does not exist yet: the function creates it

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, data):
        touch(self.src, rel, data)

    def names(self, rel=""):
        return sorted(p.name for p in (self.dst / rel).iterdir())

    def test_photos_are_numbered_alphabetically_and_labels_follow(self):
        self.put("zeta.jpg", b"Z")
        self.put("alfa.PNG", b"A")
        self.put("alfa.txt", b"0 .5 .5 .1 .1")
        self.assertEqual(move_numbered(self.src, self.dst, PH), 2)
        self.assertEqual(self.names(), ["IMG_0001.png", "IMG_0001.txt", "IMG_0002.jpg"])
        self.assertEqual((self.dst / "IMG_0001.txt").read_bytes(), b"0 .5 .5 .1 .1")
        self.assertFalse((self.src / "zeta.jpg").exists())             # moved, not copied: no second copy remains

    def test_stereo_pairs_get_the_same_number(self):
        for side in ("lx", "rx"):
            self.put(f"{side}/b.jpg", side.encode() + b"-b")
            self.put(f"{side}/a.jpg", side.encode() + b"-a")
        self.put("rx/a.txt", b"label")
        self.assertEqual(move_numbered(self.src, self.dst, ST), 4)
        self.assertEqual(self.names(), ["lx", "rx"])
        self.assertEqual(self.names("lx"), ["IMG_0001.jpg", "IMG_0002.jpg"])
        self.assertEqual(self.names("rx"), ["IMG_0001.jpg", "IMG_0001.txt", "IMG_0002.jpg"])
        self.assertEqual((self.dst / "lx/IMG_0001.jpg").read_bytes(), b"lx-a")
        self.assertEqual((self.dst / "rx/IMG_0002.jpg").read_bytes(), b"rx-b")

    def test_stereo_videos_keep_their_pairs(self):
        for side in ("lx", "rx"):
            self.put(f"{side}/b.mp4", side.encode())
            self.put(f"{side}/a.mp4", side.encode())
        self.assertEqual(move_numbered(self.src, self.dst, "stereo_video"), 4)
        self.assertEqual(self.names("lx"), ["VID_0001.mp4", "VID_0002.mp4"])
        self.assertEqual(self.names("rx"), ["VID_0001.mp4", "VID_0002.mp4"])

    def test_videos_are_numbered_vid(self):
        self.put("b.mp4", b"B")
        self.put("a.MOV", b"A")
        move_numbered(self.src, self.dst, VI)
        self.assertEqual(self.names(), ["VID_0001.mov", "VID_0002.mp4"])

    def test_other_files_are_not_moved(self):
        self.put("a.jpg", b"A")
        self.put("notes.md", b"n")
        move_numbered(self.src, self.dst, PH)
        self.assertEqual(self.names(), ["IMG_0001.jpg"])
        self.assertTrue((self.src / "notes.md").exists())

    def test_the_class_names_file_travels_with_the_labels(self):
        self.put("a.jpg", b"A")
        self.put("a.txt", b"0 .5 .5 .1 .1")
        self.put("classes.txt", b"crab\n")
        self.assertEqual(validate_media_dir(self.src, PH), [])           # classes.txt is not a label of a photo
        move_numbered(self.src, self.dst, PH)
        self.assertEqual(self.names(), ["IMG_0001.jpg", "IMG_0001.txt", "classes.txt"])

    def test_label_name(self):
        self.assertEqual(label_name("a/b.JPG"), "a/b.txt")


if __name__ == "__main__":
    unittest.main()
