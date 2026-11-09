import tempfile
import unittest
from pathlib import Path

from common.errors import AppError
from server.storage import Storage


class DatasetApprovalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Storage(self.root)
        self.datasets = self.store.library("datasets")
        self.pending = self.store.pending_root("datasets")

    def put(self, user, name, *files):
        for f in files:
            path = self.pending / user / name / f
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")

    def test_approving_publishes_the_dataset_and_clears_the_quarantine(self):
        self.put("mario", "coralli", "data.yaml", "images/a.jpg", "labels/a.txt")
        self.assertEqual(self.store.approve_dataset("mario", "coralli"), ("coralli", 1))
        self.assertTrue((self.datasets / "coralli" / "images" / "a.jpg").is_file())
        self.assertEqual(list(self.pending.iterdir()), [])                  # nothing left waiting

    def test_approving_does_not_overwrite_an_existing_dataset(self):
        self.put("mario", "coralli", "data.yaml", "images/a.jpg", "labels/a.txt")
        (self.datasets / "coralli").mkdir()
        with self.assertRaises(AppError) as ctx:
            self.store.approve_dataset("mario", "coralli")
        self.assertEqual(ctx.exception.status, 409)
        self.assertTrue((self.pending / "mario" / "coralli" / "data.yaml").is_file())      # still waiting

    def test_approving_checks_the_dataset_again(self):
        self.put("mario", "coralli", "data.yaml", "images/a.jpg")                          # the label is missing
        with self.assertRaises(AppError):
            self.store.approve_dataset("mario", "coralli")
        self.assertTrue((self.pending / "mario" / "coralli").is_dir())

    def test_rejecting_removes_the_dataset_and_clears_the_quarantine(self):
        self.put("mario", "coralli", "data.yaml", "images/a.jpg", "labels/a.txt")
        self.assertEqual(self.store.reject_dataset("mario", "coralli"), 1)
        self.assertEqual(list(self.pending.iterdir()), [])                  # nothing left waiting

    def test_a_dataset_that_is_not_waiting_is_not_found(self):
        with self.assertRaises(AppError) as ctx:
            self.store.pending_dataset_dir("mario", "nothing")
        self.assertEqual(ctx.exception.status, 404)

    def test_the_dataset_name_must_be_a_single_folder(self):
        for bad in ("../x", "a/b", ""):
            with self.subTest(bad), self.assertRaises(AppError):
                self.store.pending_dataset_dir("mario", bad)