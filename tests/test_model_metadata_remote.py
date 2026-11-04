"""Lettura dei metadati di un modello direttamente dal server (con un finto client)."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.model_metadata import fetch_remote_metadata
from tests.util import FakeServerClient

META = {"schema": 1, "species": "Pinna nobilis", "dataset": {"name": "ok"}}
PATH = "Pinna nobilis/m.pt"


def tree(**files):
    return {"Pinna nobilis": {name.replace("_", "."): data for name, data in files.items()}}


class FetchRemoteMetadataTest(unittest.TestCase):
    def test_reads_the_json_next_to_the_model(self):
        client = FakeServerClient(tree(m_pt=b"x", m_json=json.dumps(META).encode()))
        self.assertEqual(fetch_remote_metadata(client, "models", PATH), META)

    def test_it_downloads_the_json_not_the_model(self):
        client = FakeServerClient(tree(m_pt=b"x", m_json=json.dumps(META).encode()))
        fetch_remote_metadata(client, "models", PATH)
        self.assertEqual(client.downloaded, ["Pinna nobilis/m.json"])

    def test_a_model_without_metadata_gives_none(self):
        self.assertIsNone(fetch_remote_metadata(FakeServerClient(tree(m_pt=b"x")), "models", PATH))

    def test_broken_metadata_gives_none(self):
        client = FakeServerClient(tree(m_pt=b"x", m_json=b"{oops"))
        self.assertIsNone(fetch_remote_metadata(client, "models", PATH))

    def test_a_connection_problem_gives_none(self):
        class Down(FakeServerClient):
            def download(self, *args, **kwargs):
                raise OSError("server down")
        self.assertIsNone(fetch_remote_metadata(Down(tree(m_json=b"{}")), "models", PATH))


if __name__ == "__main__":
    unittest.main()