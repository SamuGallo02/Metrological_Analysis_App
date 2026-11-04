"""Scaricamento di una cartella intera dal server (con un finto client, senza rete)."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.remote_tree import download_tree, walk_remote

from tests.util import FakeServerClient

TREE = {"ds": {"data.yaml": b"names: [a]", "images": {"1.jpg": b"abc", "2.jpg": b"de"}, "labels": {}}}


class RemoteTreeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name) / "ds"
        self.client = FakeServerClient(TREE)

    def test_walk_lists_the_files_of_all_subfolders(self):
        files = walk_remote(self.client, "datasets", "ds")
        self.assertEqual(sorted(files), [("ds/data.yaml", 10), ("ds/images/1.jpg", 3), ("ds/images/2.jpg", 2)])

    def test_walk_from_the_root_has_no_leading_slash(self):
        files = walk_remote(self.client, "datasets", "")
        self.assertIn(("ds/data.yaml", 10), files)

    def test_download_recreates_the_structure(self):
        n = download_tree(self.client, "datasets", "ds", self.dest)
        self.assertEqual(n, 3)
        self.assertEqual((self.dest / "data.yaml").read_bytes(), b"names: [a]")
        self.assertEqual((self.dest / "images" / "2.jpg").read_bytes(), b"de")

    def test_progress_ends_at_the_total_size(self):
        calls = []
        download_tree(self.client, "datasets", "ds", self.dest, progress=lambda d, t: calls.append((d, t)))
        self.assertEqual(calls[-1], (15, 15))
        self.assertEqual([d for d, _t in calls], sorted(d for d, _t in calls))   # mai all'indietro

    def test_files_already_present_are_not_downloaded_again(self):
        (self.dest / "images").mkdir(parents=True)
        (self.dest / "images" / "1.jpg").write_bytes(b"abc")
        download_tree(self.client, "datasets", "ds", self.dest)
        self.assertNotIn("ds/images/1.jpg", self.client.downloaded)
        self.assertEqual(len(self.client.downloaded), 2)

    def test_empty_folder_downloads_nothing(self):
        self.assertEqual(download_tree(self.client, "datasets", "ds/labels", self.dest), 0)


if __name__ == "__main__":
    unittest.main()