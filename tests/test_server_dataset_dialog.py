"""Finestra "Scarica dataset dal server" (headless, con un finto client)."""
import os, sys, tempfile, time, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from corpse.gui.training.server_dialog import ServerDatasetDialog
from tests.util import FakeServerClient

TREE = {"ok": {"data.yaml": b"names: [a]", "images": {"1.jpg": b"abc"}},
        "mini": {"data.yaml": b"names: [b]", "images": {}}}
CATALOG = [
    {"kind": "dataset", "species": "ok", "path": "ok", "uploader": "luca", "approved_by": "admin",
     "date": "2026-11-03", "items": 1, "classes": ["Pinna nobilis", "Sparus aurata"]},
    {"kind": "dataset", "species": "mini", "path": "mini", "uploader": "mario", "approved_by": "admin",
     "date": "2026-11-02", "items": 0, "classes": []},
]


def pump(cond, secs=8):
    t = time.time()
    while time.time() - t < secs and not cond():
        app.processEvents(); time.sleep(0.02)
    app.processEvents()
    return cond()


class FailingClient:
    def catalog(self, kind):
        raise OSError("server down")


class FakeCatalogClient(FakeServerClient):
    def catalog(self, kind):
        return CATALOG


class ServerDatasetDialogTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name) / "Dataset_Training"

    def dialog(self, client):
        d = ServerDatasetDialog(client, self.dest)
        self.addCleanup(d.deleteLater)
        return d

    def test_lists_the_datasets_under_each_species(self):
        d = self.dialog(FakeCatalogClient(TREE))
        self.assertTrue(pump(lambda: d.tree.topLevelItemCount() == 3))
        rows = [(d.tree.topLevelItem(i).text(0), d.tree.topLevelItem(i).child(0).text(0)) for i in range(3)]
        self.assertEqual(rows[:2], [("Pinna nobilis", "ok"), ("Sparus aurata", "ok")])     # the same dataset, twice
        self.assertEqual(rows[2][1], "mini")                                                # no species: last group

    def test_download_needs_a_dataset_not_a_species(self):
        d = self.dialog(FakeCatalogClient(TREE))
        pump(lambda: d.tree.topLevelItemCount() == 3)
        self.assertFalse(d.btn_download.isEnabled())
        d.tree.setCurrentItem(d.tree.topLevelItem(0))                    # a species row
        self.assertFalse(d.btn_download.isEnabled())
        d.tree.setCurrentItem(d.tree.topLevelItem(0).child(0))           # a dataset
        self.assertTrue(d.btn_download.isEnabled())

    def test_downloads_the_chosen_dataset(self):
        d = self.dialog(FakeCatalogClient(TREE))
        pump(lambda: d.tree.topLevelItemCount() == 3)
        d.tree.setCurrentItem(d.tree.topLevelItem(0).child(0))
        got = []
        d.downloaded.connect(got.append)
        d.btn_download.click()
        self.assertTrue(pump(lambda: got))
        self.assertEqual(got, ["ok"])
        self.assertEqual((self.dest / "ok" / "data.yaml").read_bytes(), b"names: [a]")
        self.assertTrue((self.dest / "ok" / "images" / "1.jpg").is_file())

    def test_a_server_error_is_shown_not_raised(self):
        d = self.dialog(FailingClient())
        self.assertTrue(pump(lambda: "down" in d.status.text()))

    def test_a_dataset_inside_a_species_folder_is_downloaded_flat(self):
        leaf = "Pinna nobilis_mario_2026-11-04"
        tree = {"Pinna nobilis": {leaf: {"data.yaml": b"names: [a]", "images": {"1.jpg": b"abc"}}}}
        items = [{"kind": "dataset", "species": "x", "path": f"Pinna nobilis/{leaf}", "uploader": "mario",
                  "approved_by": "admin", "date": "2026-11-04", "items": 1, "classes": ["Pinna nobilis"]}]
        client = FakeCatalogClient(tree)
        client.catalog = lambda kind: items
        d = self.dialog(client)
        self.assertTrue(pump(lambda: d.tree.topLevelItemCount() == 1))
        self.assertEqual(d.tree.topLevelItem(0).child(0).text(0), leaf)           # only the last name is shown
        d.tree.setCurrentItem(d.tree.topLevelItem(0).child(0))
        got = []
        d.downloaded.connect(got.append)
        d.btn_download.click()
        self.assertTrue(pump(lambda: got))
        self.assertEqual(got, [leaf])                                              # flat, as the Training page expects
        self.assertTrue((self.dest / leaf / "data.yaml").is_file())


if __name__ == "__main__":
    unittest.main()