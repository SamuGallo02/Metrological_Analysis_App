"""The media are looked at by species, and the species come from the labels.

A photo of two animals carries two labels and is therefore under two species at once, while the folder the user
added stays exactly as it was: the species are a view, not a place where files are moved.

Autore: Samuele Gallo
"""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage                                       # noqa: E402
from PySide6.QtWidgets import QApplication                             # noqa: E402

from common import species                                             # noqa: E402
from common.label_store import save_labels                             # noqa: E402

from corpse.functions.users.session import Session                     # noqa: E402
from corpse.functions.users.store import LocalStore                    # noqa: E402
from corpse.gui.users import folders_local                             # noqa: E402

app = QApplication.instance() or QApplication([])


def a_photo(folder: Path, name: str) -> Path:
    path = folder / name
    QImage(40, 30, QImage.Format.Format_RGB32).save(str(path))
    return path


class SpeciesOfAFileTest(unittest.TestCase):
    def test_a_photo_with_two_animals_belongs_to_two_species(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp), "two.png")
            save_labels(photo, ["0 0.3 0.3 0.2 0.2", "1 0.7 0.7 0.2 0.2"], ["Pinna nobilis", "Posidonia oceanica"])
            species.forget(photo)
            self.assertEqual(species.species_of(photo), ["Pinna nobilis", "Posidonia oceanica"])
            groups = species.by_species([photo])
            self.assertEqual(sorted(groups), ["Pinna nobilis", "Posidonia oceanica"])
            self.assertEqual(groups["Pinna nobilis"], [photo])          # the same file, in both places
            self.assertEqual(groups["Posidonia oceanica"], [photo])

    def test_a_file_without_labels_waits_under_no_species(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp), "plain.png")
            self.assertEqual(species.species_of(photo), [])
            self.assertEqual(list(species.by_species([photo])), [species.UNNAMED])

    def test_filing_under_a_species_adds_a_label_and_moves_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp), "plain.png")
            where = photo.parent
            self.assertTrue(species.assign(photo, "Pinna nobilis"))
            self.assertEqual(species.species_of(photo), ["Pinna nobilis"])
            self.assertEqual(photo.parent, where)                       # the file never moved
            self.assertTrue(photo.is_file())
            self.assertFalse(species.assign(photo, "Pinna nobilis"))    # already there: nothing to do

    def test_a_file_can_be_filed_under_a_second_species(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp), "one.png")
            save_labels(photo, ["0 0.5 0.5 0.2 0.2"], ["Pinna nobilis"])
            species.forget(photo)
            self.assertTrue(species.assign(photo, "Posidonia oceanica"))
            self.assertEqual(species.species_of(photo), ["Pinna nobilis", "Posidonia oceanica"])
            self.assertEqual(len(species.shapes_of(photo)[0]), 2)       # the first label is untouched

    def test_several_files_at_once_and_the_species_they_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = a_photo(Path(tmp), "a.png"), a_photo(Path(tmp), "b.png")
            self.assertEqual(species.assign_many([a, b], "Pinna nobilis"), 2)
            self.assertEqual(species.common_species([a, b]), "Pinna nobilis")
            self.assertEqual(species.assign_many([a, b], "Pinna nobilis"), 0)


class SpeciesViewTest(unittest.TestCase):
    def widget(self, tmp: Path):
        session = Session(LocalStore(tmp))
        session.online, session.client = False, None
        return folders_local.LocalFoldersWidget(session)

    def test_the_photos_tab_lists_the_species_and_the_datasets_tab_the_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "dive"
            folder.mkdir()
            photo = a_photo(folder, "a.png")
            save_labels(photo, ["0 0.5 0.5 0.2 0.2", "1 0.2 0.2 0.1 0.1"], ["Pinna nobilis", "Posidonia oceanica"])
            species.forget()
            w = self.widget(Path(tmp))
            src = w.library.add_source("photo", folder)
            try:
                w.refresh()
                names = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
                self.assertEqual(names, ["Pinna nobilis", "Posidonia oceanica"])
                node = w.tree.topLevelItem(0)
                w._expanded(node)                                      # the files of that species
                self.assertEqual([node.child(i).text(0) for i in range(node.childCount())], ["a.png"])

                w.tabs.setCurrentIndex(5)                              # 'Datasets': the folder as it was added
                groups = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
                self.assertIn("Photos", groups)
                self.assertIn("Training datasets", groups)
                first = w.tree.topLevelItem(0)
                self.assertIn("dive", [first.child(i).text(0) for i in range(first.childCount())])
            finally:
                w.library.remove_source(src.id)
                w.deleteLater()

    def test_a_file_chosen_under_a_species_can_be_filed_under_another_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "dive"
            folder.mkdir()
            photo = a_photo(folder, "a.png")
            species.forget()
            w = self.widget(Path(tmp))
            src = w.library.add_source("photo", folder)
            try:
                w.refresh()
                node = w.tree.topLevelItem(0)                          # without a species, to begin with
                self.assertEqual(node.text(0), "Without a species")
                w._expanded(node)
                node.child(0).setSelected(True)
                self.assertEqual(w.selected_files(), [photo])
                self.assertTrue(w.btn_species.isEnabled())
                species.assign(photo, "Pinna nobilis")
                w.refresh()
                self.assertEqual(w.tree.topLevelItem(0).text(0), "Pinna nobilis")
            finally:
                w.library.remove_source(src.id)
                w.deleteLater()

    def test_choosing_a_species_brings_all_of_its_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "dive"
            folder.mkdir()
            files = [a_photo(folder, f"{i}.png") for i in range(3)]
            species.forget()
            w = self.widget(Path(tmp))
            src = w.library.add_source("photo", folder)
            try:
                species.assign_many(files, "Pinna nobilis")
                w.refresh()
                w.tree.topLevelItem(0).setSelected(True)
                self.assertEqual(sorted(p.name for p in w.selected_files()), ["0.png", "1.png", "2.png"])
            finally:
                w.library.remove_source(src.id)
                w.deleteLater()


if __name__ == "__main__":
    unittest.main()


class ServerSpeciesTest(unittest.TestCase):
    """The server tells the same story: the species of a file are the classes of its labels."""

    @classmethod
    def setUpClass(cls):
        from tests.util import TestServer
        cls.srv = TestServer()

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def admin(self):
        from corpse.functions.users.api import ApiClient
        c = ApiClient(self.srv.url)
        c.login("admin", "adminpass1")
        return c

    def put(self, _client, rel: str, data: bytes):
        """Puts a file straight into the library of the server, where an approved upload ends up."""
        target = Path(self.srv.data) / "store" / "library" / "photos" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def test_a_photo_with_two_species_is_listed_under_both(self):
        from tests.util import png_bytes
        c = self.admin()
        base = "Pinna nobilis"
        self.put(c, f"{base}/a.png", png_bytes())
        self.put(c, f"{base}/a.txt", b"0 0.5 0.5 0.2 0.2\n1 0.2 0.2 0.1 0.1\n")
        self.put(c, f"{base}/classes.txt", b"Pinna nobilis\nPosidonia oceanica\n")
        groups = c.species_index("photos")
        self.assertIn("Pinna nobilis", groups)
        self.assertIn("Posidonia oceanica", groups)
        self.assertEqual([f["path"] for f in groups["Pinna nobilis"]], [f"{base}/a.png"])
        self.assertEqual([f["path"] for f in groups["Posidonia oceanica"]], [f"{base}/a.png"])

    def test_a_photo_without_labels_waits_under_no_species(self):
        from tests.util import png_bytes
        c = self.admin()
        base = "Sepia officinalis"
        self.put(c, f"{base}/b.png", png_bytes())
        groups = c.species_index("photos")
        self.assertIn("", groups)
        self.assertIn(f"{base}/b.png", [f["path"] for f in groups[""]])

    def test_correcting_the_labels_changes_where_the_photo_is_seen(self):
        from tests.util import png_bytes
        c = self.admin()
        base = "Pinna nobilis"
        self.put(c, f"{base}/c.png", png_bytes())
        self.put(c, f"{base}/c.txt", b"0 0.5 0.5 0.2 0.2\n")
        self.put(c, f"{base}/classes.txt", b"Pinna nobilis\n")
        self.assertIn(f"{base}/c.png", [f["path"] for f in c.species_index("photos")["Pinna nobilis"]])
        c.save_labels("photos", f"{base}/c.png", "0 0.5 0.5 0.2 0.2\n", "Posidonia oceanica\n")
        groups = c.species_index("photos")
        self.assertIn(f"{base}/c.png", [f["path"] for f in groups["Posidonia oceanica"]])
        self.assertNotIn(f"{base}/c.png", [f["path"] for f in groups.get("Pinna nobilis", [])])

    def test_the_personal_folder_is_not_a_place_for_this_view(self):
        from corpse.functions.users.api import ApiError
        c = self.admin()
        with self.assertRaises(ApiError) as e:
            c.species_index("mine")
        self.assertEqual(e.exception.status, 400)
