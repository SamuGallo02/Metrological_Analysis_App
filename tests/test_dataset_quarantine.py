import tempfile
import unittest
from pathlib import Path

from common.errors import AppError
from server.storage import Storage


class DatasetQuarantineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Storage(Path(self.tmp.name))

    def upload(self, rel, admin=False):
        return self.store.check_new_file("datasets", rel, admin=admin, username="mario", size=10)[1]

    def test_a_dataset_uploaded_by_a_user_goes_to_quarantine(self):
        self.assertEqual(self.upload("mini/images/a.jpg"), "_pending/mario/mini/images/a.jpg")

    def test_a_dataset_uploaded_by_an_admin_is_published_directly(self):
        self.assertEqual(self.upload("mini/images/a.jpg", admin=True), "mini/images/a.jpg")

    def test_all_the_files_of_a_dataset_are_accepted(self):
        for rel in ("mini/images/a.png", "mini/labels/a.txt", "mini/data.yaml", "mini/data.yml"):
            self.assertTrue(self.upload(rel).endswith(rel))

    def test_a_dataset_file_must_be_inside_a_folder(self):
        with self.assertRaises(AppError) as ctx:
            self.upload("a.jpg")
        self.assertEqual(ctx.exception.status, 422)

    def test_a_user_can_read_the_datasets_but_not_the_quarantine(self):
        self.store.list_dir("datasets", "", admin=False)                       # allowed: the approved datasets
        for call in (lambda: self.store.list_dir("datasets", "_pending", admin=False),
                     lambda: self.store.open_file("datasets", "_pending/u/mini/data.yaml", admin=False)):
            with self.assertRaises(AppError) as ctx:
                call()
            self.assertEqual(ctx.exception.status, 403)                         # the ones waiting stay closed
        self.assertEqual(self.store.list_dir("datasets", "", admin=True)["entries"], [])