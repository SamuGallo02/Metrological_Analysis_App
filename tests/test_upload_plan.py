import tempfile
import unittest
from pathlib import Path

from common.label_store import save_labels
from corpse.functions.users.upload_plan import has_stereo_folders, kind_of, plan_media, plan_stereo


class UploadPlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def touch(self, rel, data=b"x"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_photos_and_videos_are_separate_uploads(self):
        files = [self.touch("a.jpg"), self.touch("b.PNG"), self.touch("v.mp4"), self.touch("notes.pdf")]
        plan = plan_media(files, "Pinna nobilis")
        self.assertEqual(sorted(plan), ["photos", "videos"])
        self.assertEqual([r for _l, r in plan["photos"]], ["Pinna nobilis/a.jpg", "Pinna nobilis/b.PNG"])
        self.assertEqual([r for _l, r in plan["videos"]], ["Pinna nobilis/v.mp4"])

    def test_duplicate_names_are_sent_once(self):
        plan = plan_media([self.touch("x/a.jpg"), self.touch("y/a.jpg")], "Pinna nobilis")
        self.assertEqual(len(plan["photos"]), 1)

    def test_a_label_beside_the_photo_goes_with_it(self):
        photo = self.touch("a.jpg")
        self.touch("a.txt", b"0 .5 .5 .1 .1")
        self.touch("classes.txt", b"crab\n")
        plan = plan_media([photo], "Pinna nobilis")
        self.assertEqual([r for _l, r in plan["photos"]],
                         ["Pinna nobilis/a.jpg", "Pinna nobilis/a.txt", "Pinna nobilis/classes.txt"])

    def test_the_classes_file_is_sent_once_per_folder(self):
        for n in ("a", "b"):
            self.touch(f"{n}.jpg")
            self.touch(f"{n}.txt")
        self.touch("classes.txt")
        remote = [r for _l, r in plan_media([self.root / "a.jpg", self.root / "b.jpg"], "Pinna nobilis")["photos"]]
        self.assertEqual(remote.count("Pinna nobilis/classes.txt"), 1)

    def test_labels_saved_by_the_analysis_travel_with_the_media(self):
        from unittest import mock
        import common.label_store as store
        photo = self.touch("a.jpg")
        base = self.root / "saved"
        save_labels(photo, ["0 .5 .5 .1 .1"], ["crab"], base)
        with mock.patch.object(store, "LABELS_DIR", base):
            plan = plan_media([photo], "Pinna nobilis")
        remote = [r for _l, r in plan["photos"]]
        self.assertEqual(remote, ["Pinna nobilis/a.jpg", "Pinna nobilis/a.txt", "Pinna nobilis/classes.txt"])
        sent = {r: l for l, r in plan["photos"]}
        self.assertEqual(sent["Pinna nobilis/a.txt"].read_text(), "0 .5 .5 .1 .1\n")

    def test_stereo_folder(self):
        for side in ("lx", "rx"):
            self.touch(f"s/{side}/1.jpg")
            self.touch(f"s/{side}/2.jpg")
        self.touch("s/lx/1.txt")
        self.touch("s/lx/notes.md")
        self.assertTrue(has_stereo_folders(self.root / "s"))
        remote = [r for _l, r in plan_stereo(self.root / "s", "Pinna nobilis")]
        self.assertEqual(remote, ["Pinna nobilis/lx/1.jpg", "Pinna nobilis/lx/1.txt", "Pinna nobilis/lx/2.jpg",
                                  "Pinna nobilis/rx/1.jpg", "Pinna nobilis/rx/2.jpg"])
        self.assertFalse(has_stereo_folders(self.root))

    def test_kind_of(self):
        self.assertEqual([kind_of(Path(n)) for n in ("a.JPG", "b.mov", "c.txt")], ["photos", "videos", None])


if __name__ == "__main__":
    unittest.main()
