"""Photos, stereo photos and videos through the server API: pending folder, review, catalog, labels."""
import tempfile
import unittest
from pathlib import Path

from corpse.functions.users.api import ApiClient, ApiError
from tests.util import TestServer, png_bytes

SP = "Pinna nobilis"


class MediaKindsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = TestServer()
        cls.tmp = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def user(self, name):
        c = ApiClient(self.srv.url)
        c.register(name, "password123")
        c.login(name, "password123")
        return c

    def admin(self):
        c = ApiClient(self.srv.url)
        c.login("admin", "adminpass1")
        return c

    def put(self, client, area, rel, data):
        f = self.tmp / "up.bin"
        f.write_bytes(data)
        return client.upload(area, rel, f)

    def test_stereo_photos_have_their_own_catalog(self):
        u, a = self.user("kst1"), self.admin()
        for side in ("lx", "rx"):
            self.put(u, "stereo", f"{SP}/{side}/a.png", png_bytes())
        res = u.submit_species(SP, "stereo")
        self.assertEqual((res["kind"], res["photos"], res["pending"]), ("stereo", 2, True))
        a.approve_submission(res["id"])
        mine = [i for i in u.catalog("stereo") if i["uploader"] == "kst1"]
        self.assertEqual((len(mine), mine[0]["approved_by"], mine[0]["items"]), (1, "admin", 2))
        self.assertEqual([i for i in u.catalog("photos") if i["uploader"] == "kst1"], [])
        self.assertEqual(sorted(e["name"] for e in u.list("stereo", mine[0]["path"])), ["lx", "rx"])

    def test_stereo_videos_have_their_own_area(self):
        u, a = self.user("ksv1"), self.admin()
        for side in ("lx", "rx"):
            self.put(u, "stereo_videos", f"{SP}/{side}/dive.mp4", b"v" * 40)
        self.put(u, "stereo_videos", f"{SP}/lx/dive.txt", b"3 0 0.5 0.5 0.2 0.2\n")
        res = u.submit_species(SP, "stereo_video")
        self.assertEqual((res["kind"], res["pending"]), ("stereo_video", True))
        a.approve_submission(res["id"])
        path = [i for i in u.catalog("stereo_video") if i["uploader"] == "ksv1"][0]["path"]
        self.assertEqual(sorted(e["name"] for e in u.list("stereo_videos", path)), ["lx", "rx"])
        self.assertEqual(sorted(e["name"] for e in u.list("stereo_videos", f"{path}/lx")), ["VID_0001.mp4", "VID_0001.txt"])
        self.assertEqual([i for i in u.catalog("stereo") if i["uploader"] == "ksv1"], [])
        with self.assertRaises(Exception):                                   # photos do not go in the video area
            self.put(u, "stereo_videos", f"{SP}/lx/p.png", png_bytes())

    def test_an_admin_corrects_the_labels_of_an_approved_photo(self):
        u, a = self.user("kel1"), self.admin()
        self.put(u, "photos", f"{SP}/p.png", png_bytes())
        self.put(u, "photos", f"{SP}/p.txt", b"0 0.5 0.5 0.2 0.2\n")
        res = u.submit_species(SP)
        with self.assertRaises(ApiError) as pending:                      # still waiting: nothing to edit yet
            a.save_labels("photos", f"{res['path']}/IMG_0001.png", "0 .1 .1 .1 .1\n")
        self.assertEqual(pending.exception.status, 409)
        a.approve_submission(res["id"])
        path = [i for i in u.catalog("photos") if i["uploader"] == "kel1"][0]["path"]
        saved = a.save_labels("photos", f"{path}/IMG_0001.png", "1 0.3 0.3 0.1 0.1\n", "crab\nfish\n")
        self.assertEqual(saved["path"], f"{path}/IMG_0001.txt")
        self.assertEqual(u.read_bytes("photos", f"{path}/IMG_0001.txt"), b"1 0.3 0.3 0.1 0.1\n")
        self.assertEqual(u.read_bytes("photos", f"{path}/classes.txt"), b"crab\nfish\n")

    def test_only_admins_edit_labels_and_only_of_photos(self):
        u, a = self.user("kel2"), self.admin()
        with self.assertRaises(ApiError) as e:
            u.save_labels("photos", f"{SP}/x/IMG_0001.png", "0 .1 .1 .1 .1\n")
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(ApiError) as e:
            a.save_labels("videos", f"{SP}/x/VID_0001.mp4", "0 0 .1 .1 .1 .1\n")
        self.assertEqual(e.exception.status, 422)
        with self.assertRaises(ApiError):                                  # outside the library
            a.save_labels("photos", "../../server.db", "x")

    def test_videos_and_their_labels(self):
        u, a = self.user("kvi1"), self.admin()
        self.put(u, "videos", f"{SP}/dive.mp4", b"v" * 40)
        self.put(u, "videos", f"{SP}/dive.txt", b"0 0 0.5 0.5 0.2 0.2\n")
        res = u.submit_species(SP, "video")
        self.assertEqual(res["photos"], 1)                                   # the label is not a video
        a.approve_submission(res["id"])
        path = [i for i in u.catalog("video") if i["uploader"] == "kvi1"][0]["path"]
        self.assertEqual(sorted(e["name"] for e in u.list("videos", path)), ["VID_0001.mp4", "VID_0001.txt"])

    def test_labels_stay_with_the_photo(self):
        u, a = self.user("klb1"), self.admin()
        self.put(u, "photos", f"{SP}/p.png", png_bytes())
        self.put(u, "photos", f"{SP}/p.txt", b"0 0.5 0.5 0.2 0.2\n")
        a.approve_submission(u.submit_species(SP)["id"])
        path = [i for i in u.catalog("photos") if i["uploader"] == "klb1"][0]["path"]
        self.assertEqual(u.read_bytes("photos", f"{path}/IMG_0001.txt"), b"0 0.5 0.5 0.2 0.2\n")

    def test_a_label_without_its_media_is_refused_at_submit(self):
        u = self.user("klb2")
        self.put(u, "photos", f"{SP}/p.png", png_bytes())
        self.put(u, "photos", f"{SP}/other.txt", b"0 0.5 0.5 0.2 0.2\n")
        with self.assertRaises(ApiError) as e:
            u.submit_species(SP)
        self.assertEqual(e.exception.status, 422)

    def test_the_structure_is_checked_for_the_area(self):
        u = self.user("kst2")
        with self.assertRaises(ApiError) as e:
            self.put(u, "photos", f"{SP}/lx/a.png", png_bytes())               # stereo folders are not photos
        self.assertEqual(e.exception.status, 422)
        with self.assertRaises(ApiError) as e:
            self.put(u, "videos", f"{SP}/a.png", png_bytes())
        self.assertEqual(e.exception.status, 415)

    def test_what_an_admin_sends_is_published_at_once(self):
        a = self.admin()
        self.put(a, "photos", f"{SP}/adm.png", png_bytes())
        res = a.submit_species(SP)
        self.assertFalse(res["pending"])
        item = [i for i in a.catalog("photos") if i["uploader"] == "admin"][0]
        self.assertEqual(item["approved_by"], "admin")

    def test_photos_and_stereo_of_one_species_can_wait_together(self):
        u = self.user("kst3")
        self.put(u, "photos", f"{SP}/a.png", png_bytes())
        for side in ("lx", "rx"):
            self.put(u, "stereo", f"{SP}/{side}/a.png", png_bytes())
        u.submit_species(SP, "photos")
        u.submit_species(SP, "stereo")
        kinds = sorted(s["kind"] for s in self.admin().species_submissions(status="pending") if s["username"] == "kst3")
        self.assertEqual(kinds, ["photos", "stereo"])

    def test_rejecting_deletes_the_pending_files(self):
        u, a = self.user("krj1"), self.admin()
        self.put(u, "videos", f"{SP}/x.mp4", b"v" * 20)
        a.reject_submission(u.submit_species(SP, "video")["id"])
        with self.assertRaises(ApiError):
            u.submit_species(SP, "video")                                       # nothing is waiting any more


if __name__ == "__main__":
    unittest.main()
