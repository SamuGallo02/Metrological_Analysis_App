import tempfile
import unittest
from pathlib import Path

from server.storage import Storage
from tests.util import png_bytes


class QuarantineCleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Storage(self.root)
        self.pending = self.root / "models" / "_pending"

    def put_model(self, user, name="a.pt"):
        folder = self.pending / user / "Pinna nobilis"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(b"x")
        (folder / name.replace(".pt", ".json")).write_text("{}")

    def test_approving_leaves_no_empty_folders_behind(self):
        self.put_model("mario")
        self.put_model("luca", "b.pt")
        self.store.approve_model("_pending/mario/Pinna nobilis/a.pt")
        self.assertFalse((self.pending / "mario").exists())                 # mario has nothing left
        self.assertTrue((self.pending / "luca" / "Pinna nobilis" / "b.pt").exists())
        self.store.approve_model("_pending/luca/Pinna nobilis/b.pt")
        self.assertFalse(self.pending.exists())                             # nobody waits: no quarantine folder
        self.assertTrue((self.root / "models" / "Pinna nobilis" / "a.pt").exists())

    def test_deleting_a_model_in_quarantine_also_removes_its_metadata(self):
        self.put_model("mario")
        self.store.delete("models", "_pending/mario/Pinna nobilis/a.pt")
        self.assertFalse(self.pending.exists())

    def test_a_folder_with_something_else_inside_is_kept(self):
        self.put_model("mario")
        folder = self.pending / "mario" / "Pinna nobilis"
        (folder / "note.txt").write_text("x")
        self.store.delete("models", "_pending/mario/Pinna nobilis/a.pt")
        self.assertTrue((folder / "note.txt").exists())

    def test_rejecting_the_last_photos_removes_the_quarantine(self):
        folder = self.root / "dataset_Specie" / "_pending" / "mario" / "Pinna nobilis"
        folder.mkdir(parents=True)
        (folder / "img1.png").write_bytes(png_bytes())
        self.store.reject_species("mario", "Pinna nobilis")
        self.assertFalse((self.root / "dataset_Specie" / "_pending").exists())

    def test_starting_the_server_does_not_create_the_quarantine_folders(self):
        self.assertFalse((self.root / "models" / "_pending").exists())
        self.assertFalse((self.root / "dataset_Specie" / "_pending").exists())