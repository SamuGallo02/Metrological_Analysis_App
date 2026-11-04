"""Elenco dei dataset presenti sul server (con un finto client, senza rete)."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpse.functions.training.server_data import list_server_datasets
from tests.util import FakeServerClient

TREE = {
    "ok_yaml": {"data.yaml": b"x", "images": {}},
    "ok_yml": {"data.yml": b"x"},
    "no_config": {"images": {"1.jpg": b"a"}},
    "loose.txt": b"x",
}


class ServerDatasetsTest(unittest.TestCase):
    def test_lists_folders_marking_the_ones_with_a_data_file(self):
        found = list_server_datasets(FakeServerClient(TREE))
        self.assertEqual([(d["name"], d["valid"]) for d in found],
                         [("no_config", False), ("ok_yaml", True), ("ok_yml", True)])

    def test_loose_files_are_ignored(self):
        names = [d["name"] for d in list_server_datasets(FakeServerClient(TREE))]
        self.assertNotIn("loose.txt", names)

    def test_empty_area(self):
        self.assertEqual(list_server_datasets(FakeServerClient({})), [])


if __name__ == "__main__":
    unittest.main()