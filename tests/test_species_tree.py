"""Folder structure of the photos of a species."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.errors import AppError
from server.species_tree import check_species_file, copy_numbered, validate_species_dir

SP = "Epinephelus marginatus"

def touch(root: Path, rel: str) -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")


class TestCheckSpeciesFile(unittest.TestCase):
    def test_valid_paths(self):
        self.assertEqual(check_species_file(f"{SP}/a.jpg"), (SP, "a.jpg"))                     # mono
        for side in ("lx", "rx"):
            self.assertEqual(check_species_file(f"{SP}/{side}/1723130400.PNG"),
                             (SP, side, "1723130400.PNG"))                                      # stereo
        check_species_file("Pinna nobilis/a.jpg")
        check_species_file("Genus species subspecies/a.webp")

    def assert_rejected(self, rel, status, key_start):
        with self.assertRaises(AppError) as cm:
            check_species_file(rel)
        self.assertEqual(cm.exception.status, status, rel)
        self.assertTrue(cm.exception.key.startswith(key_start), rel)

    def test_species_name(self):
        for rel in ("", "a.jpg", "epinephelus marginatus/a.jpg", "Epinephelus/a.jpg",
                    "Epinephelus_marginatus/a.jpg"):
            self.assert_rejected(rel, 422, "The first folder")

    def test_wrong_structure(self):
        bad = [SP, f"{SP}/sub/a.jpg", f"{SP}/left/a.jpg", f"{SP}/LX/a.jpg",          # cartella non ammessa, maiuscole
               f"{SP}/lx/sub/a.jpg", f"{SP}/rx/lx/a.jpg",                             # troppi livelli
               f"{SP}/FOTO/FOTO ORIGINALI/a.jpg"]                                     # la vecchia struttura
        for rel in bad:
            self.assert_rejected(rel, 422, "Wrong folder structure")

    def test_only_images(self):
        for name in ("a.txt", "a.pt", "noext", "a.mp4"):
            self.assert_rejected(f"{SP}/{name}", 415, "Extension")
            self.assert_rejected(f"{SP}/lx/{name}", 415, "Extension")

    def test_error_is_translatable(self):
        with self.assertRaises(AppError) as cm:
            check_species_file(f"{SP}/x/y/a.jpg")
        self.assertIn("mono", cm.exception.params)
        self.assertIn("Pinna nobilis/image.jpg", str(cm.exception))


class TestValidateSpeciesDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sp = Path(self.tmp.name) / SP

    def tearDown(self):
        self.tmp.cleanup()

    def test_mono_folder(self):
        touch(self.sp, "a.jpg")
        touch(self.sp, "b.jpg")
        self.assertEqual(validate_species_dir(self.sp), [])

    def test_stereo_folder_with_matching_pairs(self):
        for side in ("lx", "rx"):
            touch(self.sp, f"{side}/IMG_0001.jpg")
            touch(self.sp, f"{side}/IMG_0002.jpg")
        self.assertEqual(validate_species_dir(self.sp), [])

    def test_stereo_needs_both_sides(self):
        touch(self.sp, "rx/1.jpg")
        problems = validate_species_dir(self.sp)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].key.startswith("The stereo folder"))
        (self.sp / "lx").mkdir()                                       # un lato vuoto non conta
        self.assertEqual(len(validate_species_dir(self.sp)), 1)
        touch(self.sp, "lx/1.jpg")
        self.assertEqual(validate_species_dir(self.sp), [])

    def test_pairs_must_have_same_names(self):
        touch(self.sp, "lx/1.jpg")
        touch(self.sp, "lx/2.jpg")
        touch(self.sp, "rx/1.jpg")
        touch(self.sp, "rx/3.jpg")
        problems = validate_species_dir(self.sp)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].key.startswith("The lx and rx"))

    def test_mono_and_stereo_cannot_be_mixed(self):
        touch(self.sp, "a.jpg")
        touch(self.sp, "lx/a.jpg")
        touch(self.sp, "rx/a.jpg")
        problems = validate_species_dir(self.sp)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].key.startswith("Wrong folder structure"))

    def test_empty_or_without_images(self):
        self.sp.mkdir(parents=True)
        self.assertEqual(validate_species_dir(self.sp)[0].params["folder"], SP)
        touch(self.sp, "notes.txt")                                   # altri file non contano come foto
        self.assertEqual(len(validate_species_dir(self.sp)), 1)

    
class TestCopyNumbered(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "src"
        self.dst = Path(self.tmp.name) / "dst"          # non esiste ancora: la funzione deve crearla

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, data):
        f = self.src / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)

    def names(self, rel=""):
        return sorted(p.name for p in (self.dst / rel).iterdir())

    def test_mono_is_numbered_in_alphabetical_order(self):
        self.put("zeta.jpg", b"Z")
        self.put("alfa.PNG", b"A")
        self.assertEqual(copy_numbered(self.src, self.dst), 2)
        self.assertEqual(self.names(), ["IMG_0001.png", "IMG_0002.jpg"])
        self.assertEqual((self.dst / "IMG_0001.png").read_bytes(), b"A")
        self.assertTrue((self.src / "zeta.jpg").exists())                 # l'originale non viene toccato

    def test_stereo_pairs_get_the_same_number(self):
        for side in ("lx", "rx"):
            self.put(f"{side}/b.jpg", side.encode() + b"-b")
            self.put(f"{side}/a.jpg", side.encode() + b"-a")
        self.assertEqual(copy_numbered(self.src, self.dst), 4)
        self.assertEqual(self.names(), ["lx", "rx"])
        self.assertEqual(self.names("lx"), ["IMG_0001.jpg", "IMG_0002.jpg"])
        self.assertEqual((self.dst / "lx/IMG_0001.jpg").read_bytes(), b"lx-a")
        self.assertEqual((self.dst / "rx/IMG_0001.jpg").read_bytes(), b"rx-a")
        self.assertEqual((self.dst / "rx/IMG_0002.jpg").read_bytes(), b"rx-b")

    def test_other_files_are_not_copied(self):
        self.put("a.jpg", b"A")
        self.put("notes.txt", b"n")
        copy_numbered(self.src, self.dst)
        self.assertEqual(self.names(), ["IMG_0001.jpg"])


if __name__ == "__main__":
    unittest.main()