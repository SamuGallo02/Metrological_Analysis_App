import tempfile
import unittest
from pathlib import Path

from common.errors import AppError
from tests.util import upload_as_user
from server.db import Database
from server.storage import Storage
from server.submissions import submit_species


class SubmitSpeciesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Storage(Path(self._tmp.name))
        self.db = Database(Path(self._tmp.name) / "test.db")

    def _upload(self, rel, area="photos"):
        upload_as_user(self.store, rel, area=area)

    def test_valid_submission_is_registered(self):
        self._upload("Pinna nobilis/a.jpg")
        self._upload("Pinna nobilis/b.jpg")
        result = submit_species(self.store, self.db, "francy", "Pinna nobilis")
        self.assertEqual(result["photos"], 2)
        rows = self.db.list_submissions(username="francy")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(rows[0]["path"], "_pending/francy/Pinna nobilis")

    def test_incomplete_stereo_is_rejected(self):
        self._upload("Pinna nobilis/rx/a.jpg", "stereo")      # lx is missing
        with self.assertRaises(AppError):
            submit_species(self.store, self.db, "francy", "Pinna nobilis", "stereo")
        self.assertEqual(self.db.list_submissions(), [])                       # nessuna riga creata

    def test_double_submit_is_rejected(self):
        self._upload("Pinna nobilis/a.jpg")
        submit_species(self.store, self.db, "francy", "Pinna nobilis")
        with self.assertRaises(AppError):
            submit_species(self.store, self.db, "francy", "Pinna nobilis")
        self.assertEqual(len(self.db.list_submissions()), 1)                   # ancora una sola