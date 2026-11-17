"""The Folders page: the choice Local / Server / Groups, the local folders and the group panels.

Autore: Samuele Gallo
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QWidget

from corpse.functions.users.session import Session
from corpse.functions.users.store import LocalStore
from corpse.gui.users import folders_local, folders_page, groups_page

app = QApplication.instance() or QApplication([])


def offline_session(tmp: Path) -> Session:
    return Session(LocalStore(tmp))


class FakeClient:
    def __init__(self, groups=(), waiting=()):
        self._groups, self._waiting = list(groups), list(waiting)
        self.calls = []

    def groups(self, everyone=False):
        return self._groups

    def group_pending(self, group):
        return self._waiting

    def users(self):
        return [{"username": "mario"}, {"username": "luca"}]

    def set_member(self, *a, **k):
        self.calls.append(("member", a, k))
        return []

    def update_group(self, name, description=None, free_upload=None):
        self.calls.append(("settings", name, description, free_upload))
        return {"name": name, "description": description or "", "free_upload": bool(free_upload), "members": []}

    def delete_group(self, name, files=False):
        self.calls.append(("delete", name, files))

    def set_group_role(self, *a):
        self.calls.append(("role", a))
        return []

    def approve_group_upload(self, path):
        self.calls.append(("approve", path))
        return [path]

    def reject_group_upload(self, path):
        self.calls.append(("reject", path))

    def upload(self, area, rel, path):
        self.calls.append(("upload", area, rel))
        return {"path": rel, "pending": area == "groups"}


class ChoiceTest(unittest.TestCase):
    def test_the_page_opens_on_the_choice_and_builds_a_section_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = folders_page.FoldersPage(offline_session(Path(tmp)))
            self.assertEqual(page.stack.currentIndex(), folders_page.CHOICE)
            with mock.patch.object(folders_page, "ServerFoldersWidget", lambda s: QWidget()):
                first = page.open_section("server")
                self.assertEqual(page.stack.currentIndex(), folders_page.SECTION)
                self.assertIs(page.open_section("server"), first)       # the same widget, not a new one
            page.show_choice()
            self.assertEqual(page.stack.currentIndex(), folders_page.CHOICE)

    def test_the_three_sections_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = folders_page.FoldersPage(offline_session(Path(tmp)))
            with mock.patch.object(folders_page, "ServerFoldersWidget", lambda s: QWidget()), \
                    mock.patch.object(folders_page, "GroupsPage", lambda s: QWidget()), \
                    mock.patch.object(folders_page, "LocalFoldersWidget", lambda s: QWidget()):
                for name in ("local", "server", "groups"):
                    self.assertIsNotNone(page.open_section(name), name)


class LocalFoldersTest(unittest.TestCase):
    """The local section: the media by species, and the folders the user added under 'Datasets' (always last)."""

    def widget(self, tmp: Path):
        session = offline_session(tmp)
        return folders_local.LocalFoldersWidget(session), session

    def test_datasets_is_always_the_last_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            names = [w.tabs.tabText(i) for i in range(w.tabs.count())]
            self.assertEqual(names, ["Photos", "Stereo photos", "Videos", "Stereo videos", "YOLO models",
                                     "Datasets"])
            self.assertEqual(names, [label for label, _mode, _kind, _folder in folders_local.tabs()])

    def test_the_media_tabs_show_the_species_and_the_last_one_the_added_folders(self):
        from common.media_library import KINDS
        from common.paths import MODELS_DIR, TRAINING_DIR
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            kinds = [kind for _label, _mode, kind, _folder in folders_local.tabs()]
            self.assertEqual(kinds[:4], list(KINDS))
            self.assertEqual((w.mode, w.kind), (folders_local.BY_SPECIES, KINDS[0]))
            w.tabs.setCurrentIndex(4)
            self.assertEqual((w.mode, w.app_folder()), (folders_local.PLAIN_FOLDER, MODELS_DIR))
            w.tabs.setCurrentIndex(5)
            self.assertEqual((w.mode, w.app_folder()), (folders_local.ADDED_FOLDERS, TRAINING_DIR))
            self.assertTrue(MODELS_DIR.is_dir())                        # shown empty, never missing

    def test_a_folder_added_here_is_the_one_the_analysis_offers(self):
        from corpse.functions.analysis.library import default_library
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            folder = Path(tmp) / "dive-2026"
            folder.mkdir()
            src = w.library.add_source("photo", folder)
            try:
                w.tabs.setCurrentIndex(5)                               # the folders, as they were added
                names = []
                for i in range(w.tree.topLevelItemCount()):
                    group = w.tree.topLevelItem(i)
                    names += [group.child(c).text(0) for c in range(group.childCount())]
                self.assertIn("dive-2026", names)
                self.assertIn("dive-2026", [s.name for s in default_library().sources("photo")])
            finally:
                w.library.remove_source(src.id)

    def test_removing_a_folder_from_the_list_keeps_the_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            folder = Path(tmp) / "keep-me"
            folder.mkdir()
            (folder / "a.jpg").write_bytes(b"x")
            src = w.library.add_source("photo", folder)
            w.library.remove_source(src.id)
            self.assertNotIn("keep-me", [s.name for s in w.library.sources("photo")])
            self.assertTrue((folder / "a.jpg").is_file())

    def test_the_tree_shows_what_is_inside_the_chosen_kind(self):
        from common.paths import MODELS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            (MODELS_DIR / "example.json").write_text("{}")
            try:
                w.tabs.setCurrentIndex(4)                               # the models of the application
                names = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
                self.assertIn("example.json", names)
                w.tabs.setCurrentIndex(0)
                names = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
                self.assertNotIn("example.json", names)                 # the species, not the models
            finally:
                (MODELS_DIR / "example.json").unlink()

    def test_the_folder_of_a_kind_cannot_be_renamed_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            self.assertIsNone(w.tree.currentItem())                     # nothing selected: the kind itself
            w.tabs.setCurrentIndex(4)                                   # a folder of the application
            self.assertIsNone(w.tree.currentItem())
            self.assertFalse(w.btn_delete.isEnabled())
            self.assertFalse(w.btn_rename.isEnabled())
            self.assertTrue(w.btn_new.isEnabled())                      # but a folder can be made inside it

    def test_sending_a_folder_sends_every_file_inside(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, session = self.widget(Path(tmp))
            folder = Path(tmp) / "extra"
            (folder / "sub").mkdir(parents=True)
            (folder / "a.txt").write_text("x")
            (folder / "sub" / "b.txt").write_text("x")
            session.client = FakeClient()
            result = w._upload(folder, {"area": "groups", "prefix": "Dive"})
            sent = [c for c in session.client.calls if c[0] == "upload"]
            self.assertEqual(sorted(c[2] for c in sent), ["Dive/extra/a.txt", "Dive/extra/sub/b.txt"])
            self.assertEqual((result["files"], result["pending"]), (2, 2))


class GroupsPageTest(unittest.TestCase):
    GROUPS = [{"name": "Dive", "role": "admin", "members": [{"username": "mario", "role": "admin"},
                                                            {"username": "luca", "role": "member"}]},
              {"name": "Other", "role": "member", "members": [{"username": "ann", "role": "admin"}]}]

    def page(self, tmp: Path, groups=None):
        session = offline_session(tmp)
        page = groups_page.GroupsPage(session)
        page._fill((groups if groups is not None else self.GROUPS, ["mario", "luca", "ann"]))
        return page, session

    def test_the_groups_are_listed_and_the_administrator_is_marked(self):
        with tempfile.TemporaryDirectory() as tmp:
            page, _ = self.page(Path(tmp))
            self.assertEqual([page.list.item(i).text() for i in range(page.list.count())], ["Dive ★", "Other"])

    def test_an_administrator_of_the_group_can_manage_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            page, _ = self.page(Path(tmp))
            page.list.setCurrentRow(0)
            self.assertTrue(page.members.btn_add.isEnabled())
            self.assertTrue(page.members.btn_promote.isEnabled())
            self.assertTrue(page.settings.btn_delete.isEnabled())
            self.assertEqual([page.members.table.item(r, 0).text() for r in range(2)], ["mario", "luca"])

    def test_a_plain_member_sees_but_cannot_manage(self):
        with tempfile.TemporaryDirectory() as tmp:
            page, _ = self.page(Path(tmp))
            page.list.setCurrentRow(1)
            self.assertFalse(page.members.btn_add.isEnabled())
            self.assertFalse(page.members.btn_remove.isEnabled())
            self.assertFalse(page.settings.btn_delete.isEnabled())
            self.assertFalse(page.settings.btn_save.isEnabled())
            self.assertTrue(page.members.btn_leave.isEnabled())

    def test_without_groups_the_page_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            page, _ = self.page(Path(tmp), groups=[])
            self.assertIn("New group", page.status.text())


class GroupSettingsTest(unittest.TestCase):
    GROUP = {"name": "Dive", "role": "admin", "description": "Immersioni 2026", "free_upload": True, "members": []}

    def widget(self, tmp: Path, group=None):
        session = offline_session(tmp)
        session.client = FakeClient()
        w = groups_page.GroupSettingsWidget(session)
        w.show_group(group or self.GROUP)
        return w, session

    def test_the_settings_show_what_the_group_has(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            self.assertEqual(w.description.toPlainText(), "Immersioni 2026")
            self.assertTrue(w.free_upload.isChecked())

    def test_saving_sends_the_description_and_the_rule_on_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, session = self.widget(Path(tmp))
            w.description.setPlainText("Nuova descrizione")
            w.free_upload.setChecked(False)
            with mock.patch.object(groups_page, "run_async", lambda parent, work, ok, fail: ok(work())):
                w._save()
            self.assertIn(("settings", "Dive", "Nuova descrizione", False), session.client.calls)

    def test_deleting_asks_for_the_name_of_the_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            dialog = groups_page.DeleteGroupDialog("Dive")
            ok = dialog.buttons.button(groups_page.QDialogButtonBox.StandardButton.Ok)
            self.assertFalse(ok.isEnabled())
            dialog.typed.setText("Div")
            self.assertFalse(ok.isEnabled())
            dialog.typed.setText(" dive ")                       # the case and the spaces do not matter
            self.assertTrue(ok.isEnabled())
            self.assertFalse(dialog.delete_files())

    def test_the_deletion_passes_the_choice_about_the_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, session = self.widget(Path(tmp))
            dialog = groups_page.DeleteGroupDialog("Dive")
            dialog.files.setChecked(True)
            with mock.patch.object(groups_page, "DeleteGroupDialog", lambda name, parent=None: dialog), \
                    mock.patch.object(dialog, "exec", lambda: groups_page.QDialog.DialogCode.Accepted), \
                    mock.patch.object(groups_page, "run_async", lambda parent, work, ok, fail: ok(work())):
                w._delete()
            self.assertIn(("delete", "Dive", True), session.client.calls)


class PendingTest(unittest.TestCase):
    WAITING = [{"sender": "luca", "name": "a.png", "path": "a.png", "logical": "_pending/Dive/luca/a.png",
                "size": 10, "sent": 0}]

    def widget(self, tmp: Path, role="admin"):
        session = offline_session(tmp)
        session.client = FakeClient(waiting=self.WAITING)
        w = groups_page.PendingWidget(session)
        w.group = {"name": "Dive", "role": role}
        w._fill(self.WAITING)
        return w, session

    def test_what_is_waiting_is_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp))
            self.assertEqual((w.table.item(0, 0).text(), w.table.item(0, 1).text()), ("a.png", "luca"))

    def test_approving_sends_the_logical_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, session = self.widget(Path(tmp))
            w.table.selectRow(0)
            with mock.patch.object(groups_page, "run_async", lambda parent, work, ok, fail: ok(work())):
                w._decide(True)
            self.assertIn(("approve", "_pending/Dive/luca/a.png"), session.client.calls)

    def test_a_plain_member_cannot_approve(self):
        with tempfile.TemporaryDirectory() as tmp:
            w, _ = self.widget(Path(tmp), role="member")
            w.show_group({"name": "Dive", "role": "member"})
            self.assertFalse(w.btn_approve.isEnabled())


if __name__ == "__main__":
    unittest.main()
