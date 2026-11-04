import sqlite3
import tempfile
import unittest
from pathlib import Path

from server.db import Database


class SubmissionKindsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "server.db"

    def test_a_submission_is_about_photos_unless_said_otherwise(self):
        db = Database(self.path)
        sid = db.add_submission("mario", "Pinna nobilis", "_pending/mario/Pinna nobilis", 2)
        self.assertEqual(db.get_submission(sid)["kind"], "photos")

    def test_datasets_and_models_have_their_own_kind_and_can_be_listed_apart(self):
        db = Database(self.path)
        db.add_submission("mario", "Pinna nobilis", "_pending/mario/Pinna nobilis", 2)
        db.add_submission("mario", "coralli", "_pending/mario/coralli", 10, kind="dataset")
        db.add_submission("luca", "Sparus aurata", "_pending/luca/Sparus aurata/m.pt", 1, kind="model")
        self.assertEqual([s["species"] for s in db.list_submissions(kind="dataset")], ["coralli"])
        self.assertEqual([s["username"] for s in db.list_submissions(kind="model")], ["luca"])
        self.assertEqual(len(db.list_submissions()), 3)

    def test_the_reviewer_and_the_date_are_recorded(self):
        db = Database(self.path)
        sid = db.add_submission("mario", "coralli", "_pending/mario/coralli", 10, kind="dataset")
        row = db.review_submission(sid, "approved", "admin", path="coralli")
        self.assertEqual((row["reviewed_by"], row["kind"]), ("admin", "dataset"))
        self.assertIsNotNone(row["reviewed"])

    def test_a_database_from_a_previous_version_gets_the_kind_column(self):
        c = sqlite3.connect(self.path)                                  # the table as it was before the kinds
        c.execute("CREATE TABLE submissions(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, "
                  "species TEXT NOT NULL, path TEXT NOT NULL, status TEXT NOT NULL, "
                  "photos INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, reviewed_by TEXT, reviewed REAL)")
        c.execute("INSERT INTO submissions(username,species,path,status,photos,created) "
                  "VALUES('mario','Pinna nobilis','_pending/mario/Pinna nobilis','pending',2,1.0)")
        c.commit()
        c.close()
        (old,) = Database(self.path).list_submissions()
        self.assertEqual(old["kind"], "photos")