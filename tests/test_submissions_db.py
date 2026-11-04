"""Review of the folders uploaded by users (table submissions)."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.errors import AppError
from server.db import Database
from server.params import SUBMISSION_APPROVED, SUBMISSION_PENDING, SUBMISSION_REJECTED

SP = "Epinephelus marginatus"


class TestSubmissions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, user="francy", species=SP, photos=12):
        return self.db.add_submission(user, species, f"_pending/{user}/{species}", photos)

    def test_new_submission_is_pending(self):
        sid = self.add()
        (row,) = self.db.list_submissions()
        self.assertEqual(row["id"], sid)
        self.assertEqual(row["status"], SUBMISSION_PENDING)
        self.assertEqual(row["photos"], 12)
        self.assertIsNone(row["reviewed_by"])
        self.assertIsNone(row["reviewed"])

    def test_filters_and_order(self):
        a = self.add("francy")
        b = self.add("luca", "Pinna nobilis", 3)
        self.assertEqual([s["id"] for s in self.db.list_submissions()], [b, a])
        self.assertEqual([s["id"] for s in self.db.list_submissions(username="francy")], [a])
        self.db.review_submission(a, SUBMISSION_APPROVED, "admin")
        self.assertEqual([s["id"] for s in self.db.list_submissions(status=SUBMISSION_PENDING)], [b])
        self.assertEqual(self.db.list_submissions(username="luca", status=SUBMISSION_APPROVED), [])

    def test_approve_and_reject(self):
        a, b = self.add(), self.add("luca")
        done = self.db.review_submission(a, SUBMISSION_APPROVED, "admin")
        self.assertEqual((done["status"], done["reviewed_by"]), (SUBMISSION_APPROVED, "admin"))
        self.assertIsNotNone(done["reviewed"])
        self.assertEqual(self.db.review_submission(b, SUBMISSION_REJECTED, "admin")["status"], SUBMISSION_REJECTED)

    def test_cannot_review_twice(self):
        a = self.add()
        self.db.review_submission(a, SUBMISSION_REJECTED, "admin")
        with self.assertRaises(AppError) as cm:
            self.db.review_submission(a, SUBMISSION_APPROVED, "admin")
        self.assertEqual(cm.exception.status, 409)
        self.assertEqual(self.db.list_submissions()[0]["status"], SUBMISSION_REJECTED)      # unchanged

    def test_unknown_or_invalid(self):
        a = self.add()
        with self.assertRaises(AppError) as cm:
            self.db.review_submission(99, SUBMISSION_APPROVED, "admin")
        self.assertEqual(cm.exception.status, 404)
        with self.assertRaises(AppError) as cm:
            self.db.review_submission(a, "boh", "admin")
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual(self.db.list_submissions()[0]["status"], SUBMISSION_PENDING)       # unchanged

    def test_second_pending_submission_for_the_same_folder_is_refused(self):
        self.add()
        with self.assertRaises(AppError):
            self.add()

    def test_new_submission_is_allowed_after_the_review(self):
        sid = self.add()
        self.db.review_submission(sid, SUBMISSION_REJECTED, "admin")
        self.add()                                  # nessun errore: la prima non è più in attesa


if __name__ == "__main__":
    unittest.main()