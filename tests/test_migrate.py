"""Conversion of the old data folder layout into store/ (history kept, the app's own folders untouched)."""
import tempfile
import unittest
from pathlib import Path

from common.params import LOCAL_FOLDER_NAMES
from server.db import Database
from server.migrate import migrate_legacy
from server.storage import Storage

N = LOCAL_FOLDER_NAMES


def touch(root: Path, rel: str, data: bytes = b"x") -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "server.db")

    def approved(self, kind, species, path, user="mario"):
        sid = self.db.add_submission(user, species, f"_pending/{user}/{species}", 1, kind=kind)
        self.db.review_submission(sid, "approved", "admin", path=path)
        return sid

    def test_photos_and_stereo_go_to_their_own_areas_and_the_history_follows(self):
        touch(self.root, f"{N['species']}/Pinna nobilis/Pinna nobilis_mario_2026-10-01/IMG_0001.jpg")
        touch(self.root, f"{N['species']}/Pinna nobilis/Pinna nobilis_ugo_2026-10-02/lx/IMG_0001.jpg")
        touch(self.root, f"{N['species']}/Pinna nobilis/Pinna nobilis_ugo_2026-10-02/rx/IMG_0001.jpg")
        photos = self.approved("photos", "Pinna nobilis", "Pinna nobilis/Pinna nobilis_mario_2026-10-01")
        stereo = self.approved("photos", "Pinna nobilis", "Pinna nobilis/Pinna nobilis_ugo_2026-10-02", "ugo")
        migrate_legacy(self.root, self.db)
        lib = self.root / "store" / "library"
        self.assertTrue((lib / "photos/Pinna nobilis/Pinna nobilis_mario_2026-10-01/IMG_0001.jpg").is_file())
        self.assertTrue((lib / "stereo/Pinna nobilis/Pinna nobilis_ugo_2026-10-02/lx/IMG_0001.jpg").is_file())
        self.assertEqual(self.db.get_submission(photos)["kind"], "photos")
        row = self.db.get_submission(stereo)
        self.assertEqual((row["kind"], row["reviewed_by"], row["username"]), ("stereo", "admin", "ugo"))   # history kept
        self.assertFalse((self.root / N["species"]).exists())                  # the old folder is gone

    def test_waiting_uploads_move_to_the_pending_folders(self):
        touch(self.root, f"{N['species']}/_pending/mario/Pinna nobilis/a.jpg")
        touch(self.root, f"{N['species']}/_pending/ugo/Sparus aurata/lx/a.jpg")
        touch(self.root, f"{N['species']}/_pending/ugo/Sparus aurata/rx/a.jpg")
        self.db.add_submission("mario", "Pinna nobilis", "_pending/mario/Pinna nobilis", 1)
        sid = self.db.add_submission("ugo", "Sparus aurata", "_pending/ugo/Sparus aurata", 2)
        migrate_legacy(self.root, self.db)
        pend = self.root / "store" / "pending"
        self.assertTrue((pend / "photos/mario/Pinna nobilis/a.jpg").is_file())
        self.assertTrue((pend / "stereo/ugo/Sparus aurata/lx/a.jpg").is_file())
        self.assertEqual(self.db.get_submission(sid)["kind"], "stereo")
        # and the review still finds them
        store = Storage(self.root)
        store.pending_media_dir("ugo", "Sparus aurata", "stereo")

    def test_models_datasets_and_personal_folders(self):
        touch(self.root, f"{N['models']}/_pending/mario/Pinna nobilis/m.pt")
        touch(self.root, f"{N['models']}/Pinna nobilis/ok.pt")
        touch(self.root, f"{N['models']}/best.pt")                              # the app's own local model
        touch(self.root, f"{N['training']}/_pending/mario/coralli/data.yaml")
        touch(self.root, f"{N['training']}/Pinna nobilis/Pinna nobilis_mario_2026-10-01/data.yaml")
        touch(self.root, f"{N['training']}/my_local_training/data.yaml")        # the app's own local dataset
        self.approved("dataset", "coralli", "Pinna nobilis/Pinna nobilis_mario_2026-10-01")
        touch(self.root, f"{N['users']}/mario/notes.md")
        migrate_legacy(self.root, self.db)
        s = self.root / "store"
        self.assertTrue((s / "pending/models/mario/Pinna nobilis/m.pt").is_file())
        self.assertTrue((s / "library/models/Pinna nobilis/ok.pt").is_file())
        self.assertTrue((s / "pending/datasets/mario/coralli/data.yaml").is_file())
        self.assertTrue((s / "library/datasets/Pinna nobilis/Pinna nobilis_mario_2026-10-01/data.yaml").is_file())
        self.assertTrue((s / "mine/mario/notes.md").is_file())
        self.assertTrue((self.root / N["models"] / "best.pt").is_file())            # local data is never touched
        self.assertTrue((self.root / N["training"] / "my_local_training" / "data.yaml").is_file())

    def test_running_it_twice_changes_nothing(self):
        touch(self.root, f"{N['species']}/Pinna nobilis/Pinna nobilis_mario_2026-10-01/IMG_0001.jpg")
        migrate_legacy(self.root, self.db)
        migrate_legacy(self.root, self.db)
        self.assertTrue((self.root / "store/library/photos/Pinna nobilis/Pinna nobilis_mario_2026-10-01/IMG_0001.jpg").is_file())

    def test_a_clean_data_folder_needs_no_migration(self):
        self.assertEqual(migrate_legacy(self.root, self.db), [])


class AdoptLocalServerDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local = Path(self.tmp.name) / "Dataset_Locale"
        self.data = Path(self.tmp.name) / "server_data"
        Database(self.local / "server.db")                       # creates the folder and the database
        touch(self.local, "store/library/photos/Pinna nobilis/a.jpg")
        touch(self.local, "logs/server.log")
        touch(self.local, "dataset_Foto_Stereo/mine.jpg")        # the app's own data
        touch(self.local, "models/best.pt")

    def test_only_the_servers_files_move(self):
        from server.migrate import adopt_local_server_data
        adopt_local_server_data(self.local, self.data)
        self.assertTrue((self.data / "server.db").is_file())
        self.assertTrue((self.data / "store/library/photos/Pinna nobilis/a.jpg").is_file())
        self.assertTrue((self.data / "logs/server.log").is_file())
        self.assertFalse((self.local / "server.db").exists())
        self.assertFalse((self.local / "store").exists())
        self.assertTrue((self.local / "dataset_Foto_Stereo/mine.jpg").is_file())
        self.assertTrue((self.local / "models/best.pt").is_file())

    def test_it_runs_once_and_never_overwrites(self):
        from server.migrate import adopt_local_server_data
        adopt_local_server_data(self.local, self.data)
        self.assertEqual(adopt_local_server_data(self.local, self.data), [])
        Database(self.local / "server.db")                       # a new database appears in the old place
        notes = adopt_local_server_data(self.local, self.data)
        self.assertTrue(notes)
        self.assertTrue((self.local / "server.db").exists())

    def test_the_same_folder_is_left_alone(self):
        from server.migrate import adopt_local_server_data
        self.assertEqual(adopt_local_server_data(self.local, self.local), [])
        self.assertTrue((self.local / "server.db").exists())

    def test_the_legacy_layout_is_migrated_on_the_way(self):
        from server.migrate import adopt_local_server_data
        touch(self.local, f"{N['users']}/mario/note.txt")
        adopt_local_server_data(self.local, self.data)
        self.assertTrue((self.data / "store/mine/mario/note.txt").is_file())
        self.assertFalse((self.local / N["users"]).exists())


if __name__ == "__main__":
    unittest.main()
