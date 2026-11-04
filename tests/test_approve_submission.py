import tempfile
import unittest
from datetime import date
from pathlib import Path

from common.errors import AppError
from tests.util import upload_as_user
from server.db import Database
from server.storage import Storage
from server.params import AREA_DIRS
from server.submissions import approve_submission, reject_submission, submit_species


class ReviewSubmissionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Storage(Path(self._tmp.name))
        self.db = Database(Path(self._tmp.name) / "test.db")       # stessa riga degli altri test

    def _upload(self, rel):
        upload_as_user(self.store, rel)

    def _submit(self):
        self._upload("Pinna nobilis/a.jpg")
        return submit_species(self.store, self.db, "francy", "Pinna nobilis")["id"]

    def test_approval_moves_photos_and_updates_the_row(self):
        sid = self._submit()
        result = approve_submission(self.store, self.db, sid, "admin")
        self.assertEqual(result["photos"], 1)
        self.assertEqual(result["folder"], f"Pinna nobilis_francy_{date.today().isoformat()}")
        row = self.db.get_submission(sid)
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["reviewed_by"], "admin")
        self.assertEqual(row["path"], f"Pinna nobilis/{result['folder']}")

    def test_cannot_approve_twice(self):
        sid = self._submit()
        approve_submission(self.store, self.db, sid, "admin")
        with self.assertRaises(AppError):
            approve_submission(self.store, self.db, sid, "admin")

    def test_unknown_submission(self):
        with self.assertRaises(AppError):
            approve_submission(self.store, self.db, 999, "admin")

    def test_failed_approval_leaves_the_submission_pending(self):
        sid = self._submit()
        self._upload("Pinna nobilis/lx/b.jpg")                      # dopo l'invio mescola mono e stereo
        with self.assertRaises(AppError):
            approve_submission(self.store, self.db, sid, "admin")
        self.assertEqual(self.db.get_submission(sid)["status"], "pending")

    def test_rejection_deletes_the_photos_and_keeps_the_row(self):
        sid = self._submit()
        result = reject_submission(self.store, self.db, sid, "admin")
        self.assertEqual(result["photos"], 1)
        self.assertEqual(self.db.get_submission(sid)["status"], "rejected")
        with self.assertRaises(AppError):                                # le foto non ci sono più
            self.store.pending_species_dir("francy", "Pinna nobilis")
        species_dir = self.store.root / AREA_DIRS["species"] / "Pinna nobilis"
        self.assertFalse(species_dir.exists())                           # e nulla è entrato nel dataset

    def test_cannot_reject_an_approved_submission(self):
        sid = self._submit()
        approve_submission(self.store, self.db, sid, "admin")
        with self.assertRaises(AppError):
            reject_submission(self.store, self.db, sid, "admin")
        self.assertEqual(self.db.get_submission(sid)["status"], "approved")

    def test_cannot_approve_a_rejected_submission(self):
        sid = self._submit()
        reject_submission(self.store, self.db, sid, "admin")
        with self.assertRaises(AppError):
            approve_submission(self.store, self.db, sid, "admin")


if __name__ == "__main__":
    unittest.main()