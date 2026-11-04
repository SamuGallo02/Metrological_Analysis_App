import tempfile
import unittest
from pathlib import Path

from common.errors import AppError
from server.db import Database
from server.storage import Storage
from server.submissions import approve_submission, reject_submission, submit_dataset, submit_model


class SubmitDatasetAndModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Storage(self.root)
        self.db = Database(self.root / "server.db")

    def put(self, rel, data=b"x"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put_dataset(self, user="mario", name="coralli"):
        for f in ("data.yaml", "images/a.jpg", "labels/a.txt"):
            self.put(f"dataset_Training/_pending/{user}/{name}/{f}")

    def put_model(self, user="mario"):
        self.put(f"models/_pending/{user}/Pinna nobilis/m.pt")
        self.put(f"models/_pending/{user}/Pinna nobilis/m.json", b"{}")

    def test_a_valid_dataset_is_registered_as_waiting(self):
        self.put_dataset()
        result = submit_dataset(self.store, self.db, "mario", "coralli")
        row = self.db.get_submission(result["id"])
        self.assertEqual((row["kind"], row["species"], row["status"], row["photos"]),
                         ("dataset", "coralli", "pending", 1))

    def test_an_invalid_dataset_is_not_registered(self):
        self.put("dataset_Training/_pending/mario/coralli/images/a.jpg")        # no data.yaml and no label
        with self.assertRaises(AppError):
            submit_dataset(self.store, self.db, "mario", "coralli")
        self.assertEqual(self.db.list_submissions(), [])

    def test_the_same_dataset_cannot_wait_twice(self):
        self.put_dataset()
        submit_dataset(self.store, self.db, "mario", "coralli")
        with self.assertRaises(AppError) as ctx:
            submit_dataset(self.store, self.db, "mario", "coralli")
        self.assertEqual(ctx.exception.status, 409)

    def test_approving_a_dataset_publishes_it_and_records_who_and_when(self):
        self.put_dataset()
        sid = submit_dataset(self.store, self.db, "mario", "coralli")["id"]
        approve_submission(self.store, self.db, sid, "admin")
        row = self.db.get_submission(sid)
        self.assertEqual((row["status"], row["reviewed_by"]), ("approved", "admin"))
        self.assertRegex(row["path"], r"^coralli/coralli_mario_\d{4}-\d{2}-\d{2}$")
        self.assertIsNotNone(row["reviewed"])
        self.assertTrue((self.root / "dataset_Training" / row["path"] / "data.yaml").is_file())

    def test_rejecting_a_dataset_removes_it_and_keeps_the_record(self):
        self.put_dataset()
        sid = submit_dataset(self.store, self.db, "mario", "coralli")["id"]
        reject_submission(self.store, self.db, sid, "admin")
        self.assertEqual(self.db.get_submission(sid)["status"], "rejected")
        self.assertFalse((self.root / "dataset_Training" / "_pending").exists())

    def test_a_model_is_registered_and_approving_it_moves_it_with_its_metadata(self):
        self.put_model()
        result = submit_model(self.store, self.db, "mario", "Pinna nobilis", "m.pt")
        row = self.db.get_submission(result["id"])
        self.assertEqual((row["kind"], row["species"], row["status"]), ("model", "Pinna nobilis", "pending"))
        approve_submission(self.store, self.db, result["id"], "admin")
        row = self.db.get_submission(result["id"])
        self.assertEqual((row["status"], row["reviewed_by"], row["path"]), ("approved", "admin", "Pinna nobilis/m.pt"))
        self.assertTrue((self.root / "models" / "Pinna nobilis" / "m.pt").is_file())
        self.assertTrue((self.root / "models" / "Pinna nobilis" / "m.json").is_file())
        self.assertFalse((self.root / "models" / "_pending").exists())

    def test_a_model_that_was_not_uploaded_is_not_found(self):
        with self.assertRaises(AppError) as ctx:
            submit_model(self.store, self.db, "mario", "Pinna nobilis", "m.pt")
        self.assertEqual(ctx.exception.status, 404)

    def test_rejecting_a_model_removes_it_with_its_metadata(self):
        self.put_model()
        sid = submit_model(self.store, self.db, "mario", "Pinna nobilis", "m.pt")["id"]
        reject_submission(self.store, self.db, sid, "admin")
        self.assertEqual(self.db.get_submission(sid)["status"], "rejected")
        self.assertFalse((self.root / "models" / "_pending").exists())

    def test_the_kinds_are_listed_apart(self):
        self.put_dataset()
        self.put_model("luca")
        submit_dataset(self.store, self.db, "mario", "coralli")
        submit_model(self.store, self.db, "luca", "Pinna nobilis", "m.pt")
        self.assertEqual([s["username"] for s in self.db.list_submissions(kind="dataset")], ["mario"])
        self.assertEqual([s["username"] for s in self.db.list_submissions(kind="model")], ["luca"])
        self.assertEqual(self.db.list_submissions(kind="photos"), [])

    def test_an_admin_model_is_recorded_as_approved_at_once(self):
        self.put("models/Pinna nobilis/m.pt")                                     # published directly
        result = submit_model(self.store, self.db, "admin", "Pinna nobilis", "m.pt", admin=True)
        row = self.db.get_submission(result["id"])
        self.assertEqual((row["status"], row["reviewed_by"], row["path"]), ("approved", "admin", "Pinna nobilis/m.pt"))
        self.assertFalse(result["pending"])
        self.assertEqual(self.db.list_submissions(status="pending"), [])

    def test_an_admin_dataset_is_recorded_as_approved_at_once(self):
        for f in ("data.yaml", "images/a.jpg", "labels/a.txt"):
            self.put(f"dataset_Training/coralli/{f}")
        result = submit_dataset(self.store, self.db, "admin", "coralli", admin=True)
        row = self.db.get_submission(result["id"])
        self.assertEqual((row["status"], row["reviewed_by"], row["path"]), ("approved", "admin", "coralli"))
        self.assertFalse(result["pending"])

    def test_an_admin_dataset_is_checked_too(self):
        self.put("dataset_Training/coralli/images/a.jpg")                         # no data.yaml and no label
        with self.assertRaises(AppError):
            submit_dataset(self.store, self.db, "admin", "coralli", admin=True)
        self.assertEqual(self.db.list_submissions(), [])