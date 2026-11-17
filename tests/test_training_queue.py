"""Training asked of the server: the queue, who may do what, and the worker that takes the jobs."""
import tempfile
import unittest
from pathlib import Path

from corpse.functions.users.api import ApiClient, ApiError
from tests.util import TestServer


class TrainingQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = TestServer()
        cls.tmp = Path(tempfile.mkdtemp())
        a = ApiClient(cls.srv.url)
        a.login("admin", "adminpass1")
        f = cls.tmp / "data.yaml"
        f.write_text("names: [crab]\n")
        a.upload("datasets", "set1/data.yaml", f)          # an admin publishes a dataset straight away

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

    def test_a_user_asks_and_sees_only_their_own_requests(self):
        u, other = self.user("tq1"), self.user("tq2")
        job = u.request_training("set1", "yolo11n-seg.pt", epochs=5, species="Pinna nobilis")
        self.assertEqual((job["status"], job["dataset"], job["username"]), ("queued", "set1", "tq1"))
        self.assertEqual([j["id"] for j in u.training_jobs()], [job["id"]])
        self.assertEqual(other.training_jobs(), [])
        self.assertIn(job["id"], [j["id"] for j in self.admin().training_jobs(everyone=True)])

    def test_an_unknown_dataset_is_refused(self):
        with self.assertRaises(ApiError) as e:
            self.user("tq3").request_training("nowhere", "yolo11n-seg.pt")
        self.assertEqual(e.exception.status, 404)

    def test_the_worker_takes_one_job_at_a_time_and_reports_the_result(self):
        u, a = self.user("tq4"), self.admin()
        job = u.request_training("set1", "yolo11n-seg.pt", epochs=1)
        taken = a.claim_training("gpu-1")
        self.assertEqual(taken["id"], job["id"])
        self.assertEqual((taken["status"], taken["worker"]), ("running", "gpu-1"))
        self.assertIsNone(a.claim_training("gpu-2"))                     # nothing else waiting
        a.update_training(job["id"], message="epoch 1/1")
        done = a.update_training(job["id"], status="done", model="Pinna nobilis/m.pt",
                                 metrics={"mAP50": 0.91})
        self.assertEqual(done["status"], "done")
        self.assertIn("0.91", done["metrics"])
        self.assertEqual([j["status"] for j in u.training_jobs()], ["done"])

    def test_only_an_administrator_is_a_worker(self):
        u = self.user("tq5")
        for call in (lambda: u.claim_training("x"), lambda: u.update_training(1, status="done")):
            with self.assertRaises(ApiError) as e:
                call()
            self.assertEqual(e.exception.status, 403)

    def test_a_waiting_request_can_be_cancelled_by_its_owner_only(self):
        u, other, a = self.user("tq6"), self.user("tq7"), self.admin()
        job = u.request_training("set1", "yolo11n-seg.pt")
        with self.assertRaises(ApiError) as e:
            other.cancel_training(job["id"])
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(u.cancel_training(job["id"])["status"], "cancelled")
        while True:                                                      # a cancelled job is never given out
            taken = a.claim_training("gpu-1")
            if taken is None:
                break
            self.assertNotEqual(taken["id"], job["id"])
            a.update_training(taken["id"], status="failed", message="")
        with self.assertRaises(ApiError) as e:
            u.cancel_training(job["id"])
        self.assertEqual(e.exception.status, 409)

    def test_a_running_training_cannot_be_cancelled(self):
        u, a = self.user("tq8"), self.admin()
        job = u.request_training("set1", "yolo11n-seg.pt")
        a.claim_training("gpu-1")
        with self.assertRaises(ApiError) as e:
            u.cancel_training(job["id"])
        self.assertEqual(e.exception.status, 409)
        a.update_training(job["id"], status="failed", message="out of memory")


if __name__ == "__main__":
    unittest.main()
