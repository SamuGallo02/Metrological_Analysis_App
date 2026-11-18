"""Improvement of a photo asked of the server: the queue, who may do what, and what happens to the file here.

Autore: Samuele Gallo
"""
import tempfile
import unittest
from pathlib import Path

from common.image_enhance import enhanced_path
from common.label_store import find_labels, save_labels
from common.params import ORIGINALS_DIR

from corpse.functions.users import enhance
from corpse.functions.users.api import ApiClient, ApiError
from tests.util import TestServer, png_bytes


class EnhanceQueueTest(unittest.TestCase):
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

    def drain(self):
        """Empties the queue, so a test that watches the worker sees only its own job."""
        a = self.admin()
        for job in a.enhance_jobs(everyone=True, status="queued"):
            a.cancel_enhance(job["id"])

    def photo(self, name="a.png", body=None):
        f = self.tmp / name
        f.write_bytes(body if body is not None else png_bytes())
        return f

    def test_the_file_goes_to_the_personal_folder_and_the_job_waits(self):
        u = self.user("en1")
        job = enhance.send(u, self.photo("en1.png"))
        self.assertEqual((job["status"], job["username"], job["area"]), ("queued", "en1", "mine"))
        self.assertTrue(job["path"].startswith("improve/"))
        self.assertTrue(job["path"].endswith("en1.png"))
        self.assertEqual([j["id"] for j in u.enhance_jobs()], [job["id"]])

    def test_a_file_that_is_not_there_is_refused(self):
        u = self.user("en2")
        with self.assertRaises(ApiError) as e:
            u.request_enhance("improve/nowhere.png")
        self.assertEqual(e.exception.status, 404)

    def test_nobody_sees_or_cancels_the_requests_of_somebody_else(self):
        u, other = self.user("en3"), self.user("en4")
        job = enhance.send(u, self.photo("en3.png"))
        self.assertEqual(other.enhance_jobs(), [])
        with self.assertRaises(ApiError) as e:
            other.cancel_enhance(job["id"])
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(u.cancel_enhance(job["id"])["status"], "cancelled")

    def test_only_the_worker_takes_the_jobs(self):
        self.drain()
        u, a = self.user("en5"), self.admin()
        job = enhance.send(u, self.photo("en5.png"))
        with self.assertRaises(ApiError) as e:
            u.claim_enhance("laptop")
        self.assertEqual(e.exception.status, 403)
        taken = a.claim_enhance("gpu-1")
        self.assertEqual((taken["id"], taken["status"], taken["worker"]), (job["id"], "running", "gpu-1"))
        self.assertIsNone(a.claim_enhance("gpu-2"))                      # one at a time
        done = a.update_enhance(job["id"], status="done", result="improve/enhanced/en5.png")
        self.assertEqual((done["status"], done["result"]), ("done", "improve/enhanced/en5.png"))
        self.assertTrue(enhance.done(done))

    def test_a_running_job_cannot_be_cancelled(self):
        self.drain()
        u, a = self.user("en6"), self.admin()
        job = enhance.send(u, self.photo("en6.png"))
        a.claim_enhance("gpu-1")
        with self.assertRaises(ApiError) as e:
            u.cancel_enhance(job["id"])
        self.assertEqual(e.exception.status, 409)

    def test_the_improved_file_comes_back_and_is_added_or_replaces_the_original(self):
        self.drain()
        u, a = self.user("en7"), self.admin()
        media = self.photo("en7.png")
        original = media.read_bytes()
        save_labels(media, ["0 0.5 0.5 0.2 0.2"], ["crab"])
        job = enhance.send(u, media)
        a.claim_enhance("gpu-1")
        better = self.tmp / "better.png"
        better.write_bytes(png_bytes())            # what the worker would send back
        u.upload("mine", "improve/enhanced/en7.png", better)
        job = enhance.state(u, a.update_enhance(job["id"], status="done", result="improve/enhanced/en7.png"))
        got = enhance.collect(u, job, self.tmp / "back")
        self.assertEqual(got.read_bytes(), better.read_bytes())

        added = enhance.keep(media, got, enhance.ADD)
        self.assertEqual(added, enhanced_path(media))
        self.assertEqual(added.read_bytes(), better.read_bytes())
        self.assertEqual(media.read_bytes(), original)                # the original is untouched
        self.assertIsNotNone(find_labels(added))                         # the copy keeps the labels

        kept = enhance.keep(media, got, enhance.REPLACE)
        self.assertEqual(kept, media)
        self.assertEqual(media.read_bytes(), better.read_bytes())
        self.assertEqual((media.parent / ORIGINALS_DIR / media.name).read_bytes(), original)

    def test_cleaning_up_removes_both_files_from_the_server(self):
        u = self.user("en8")
        job = enhance.send(u, self.photo("en8.png"))
        enhance.cleanup(u, job)
        self.assertNotIn("en8.png", [f["name"] for f in u.list("mine", "improve")])
