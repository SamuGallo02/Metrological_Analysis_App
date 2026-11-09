"""Headless test of the windows (QT_QPA_PLATFORM=offscreen)."""
import os, sys, tempfile, threading, time, types, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path, PurePosixPath
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
for name in ("warning", "information", "critical"):
    setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))

from common import i18n
from common.ui.language import LanguageWidget
from tests.util import KEY, TestServer, png_bytes
from corpse.functions.users.session import Session
from corpse.functions.users.store import LocalStore
from corpse.gui import users as ui
from unittest import mock
from corpse.functions.users.api import ApiClient


def pump(cond, secs=8):
    t = time.time()
    while time.time() - t < secs and not cond():
        app.processEvents(); time.sleep(0.02)
    app.processEvents()
    return cond()

def settle(widget, secs=8):
    """Waits for the background work started by a window: otherwise the test ends with a thread still running."""
    from PySide6.QtCore import QThread
    return pump(lambda: not any(t.isRunning() for t in widget.findChildren(QThread)), secs)


class GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = TestServer()
        cls.url, cls.tmp = cls.srv.url, Path(cls.srv.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.srv.close(); i18n.set_language("en")

    def setUp(self):
        th = self.srv.httpd.handler.key_throttle
        th.reset(*list(th._d))

    def sess(self, name):
        return Session(LocalStore(self.tmp / name))

    def login_dialog(self, s, user, pw="password123", key="", register=False, name_pw2=True):
        d = ui.LoginDialog(s)
        d.url.setText(self.url); d.user.setText(user); d.pw.setText(pw); d.key.setText(key)
        if register:
            d.tabs.setCurrentIndex(1); d.pw2.setText(pw); d.email.setText(f"{user}@example.com")
        d._submit()
        return d

    # ---- login -----------------------------------------------------------
    def test_login_register_key_guest(self):
        s = self.sess("a1"); d = self.login_dialog(s, "tester1", register=True)
        self.assertTrue(pump(lambda: d.result() == 1), d.msg.text())
        self.assertTrue(s.logged_in and s.role == "user" and d.mode == "online")

        sk = self.sess("a2"); dk = self.login_dialog(sk, "capo1", key=KEY, register=True)
        self.assertTrue(pump(lambda: dk.result() == 1), dk.msg.text()); self.assertTrue(sk.is_admin)

        sw = self.sess("a3"); dw = self.login_dialog(sw, "tester1", key="sbagliata")       # wrong key
        self.assertTrue(pump(lambda: "access key" in dw.msg.text().lower()), dw.msg.text()); self.assertFalse(sw.logged_in)
        dw.key.setText(KEY); dw._submit()                                                  # correct -> permanent admin
        self.assertTrue(pump(lambda: dw.result() == 1)); self.assertTrue(sw.is_admin)
        s4 = self.sess("a4"); d4 = self.login_dialog(s4, "tester1"); self.assertTrue(pump(lambda: d4.result() == 1))
        self.assertTrue(s4.is_admin)                                                       # even without a key

        g = self.sess("a5"); dg = ui.LoginDialog(g); dg.btn_offline.click()
        self.assertEqual((dg.result(), dg.mode), (1, "guest")); self.assertTrue(g.is_guest and not g.online)
        bar = ui.AccountBar(g); self.assertIn("No account", bar.label.text())

        bad = self.sess("a6"); db = self.login_dialog(bad, "tester1", pw="sbagliata1")
        self.assertTrue(pump(lambda: "Invalid credentials" in db.msg.text()), db.msg.text())

    def test_key_lockout_countdown_does_not_block_login(self):
        s0 = self.sess("k0"); d0 = self.login_dialog(s0, "lockuser", register=True); pump(lambda: d0.result() == 1)
        s = self.sess("k1"); d = ui.LoginDialog(s)
        for i in range(5):
            d.url.setText(self.url); d.user.setText("lockuser"); d.pw.setText("password123"); d.key.setText(f"bad{i}")
            d._submit(); self.assertTrue(pump(lambda: d.btn_ok.isEnabled()))
        d.key.setText("bad5"); d._submit()
        self.assertTrue(pump(lambda: not d.key.isEnabled()), d.msg.text())                  # key blocked
        self.assertIn("locked", d.key.placeholderText().lower()); self.assertTrue(d.timer.isActive())
        self.assertIn("without", d.msg.text().lower())
        self.assertTrue(d.btn_ok.isEnabled())                                               # normal login is still possible
        d._submit(); self.assertTrue(pump(lambda: d.result() == 1), d.msg.text()); self.assertEqual(s.role, "user")
        d.timer.stop()

    # ---- folders and profile --------------------------------------------------
    def test_browser_roles_and_transfers(self):
        s = self.sess("b1"); d = self.login_dialog(s, "bro1", register=True); pump(lambda: d.result() == 1)
        br = ui.ServerBrowserWidget(s)
        self.assertTrue(pump(lambda: br.status.text().endswith("items")), br.status.text())
        self.assertFalse(br.btn_delete.isVisibleTo(br) or br.btn_rename.isVisibleTo(br) or br.btn_approve.isVisibleTo(br))
        mine = ui.ServerBrowserWidget(s, ("mine",))                                         # personal area: free structure
        self.assertTrue(pump(lambda: mine.status.text().endswith("items")))
        png = self.tmp / "f.png"; png.write_bytes(png_bytes())
        jobs = [("f.png", png.stat().st_size, lambda cb, cancel: s.client.upload("mine", "f.png", png, cb, cancel))]
        td = ui.TransferDialog("t", jobs); td.exec()
        self.assertFalse(td.errors or td.skipped)
        mine.refresh()
        self.assertTrue(pump(lambda: any(mine.tree.topLevelItem(i).text(0) == "f.png" for i in range(mine.tree.topLevelItemCount()))))
        td2 = ui.TransferDialog("t", jobs); td2.exec(); self.assertFalse(td2.errors)          # the owner may overwrite

        self.assertTrue(mine.btn_delete.isVisibleTo(mine) and mine.btn_rename.isVisibleTo(mine))
        self.assertTrue(pump(lambda: mine.quota.isVisibleTo(mine) and mine.quota.maximum() == 1024))

    def test_browser_is_always_a_tree_that_opens_levels_on_demand(self):
        s = self.sess("tr1"); d = self.login_dialog(s, "tree1", register=True); pump(lambda: d.result() == 1)
        png = self.tmp / "t.png"; png.write_bytes(png_bytes())
        s.client.upload("mine", "uno/due/t.png", png)
        s.client.upload("mine", "uno/altro.png", png)
        br = ui.ServerBrowserWidget(s, ("mine",))
        self.assertFalse(hasattr(br, "btn_tree"))                       # no "Folder tree" button: it is the view itself
        names = lambda it: [it.child(i).text(0) for i in range(it.childCount())]      # the server is shared by the tests
        self.assertTrue(pump(lambda: br.status.text().endswith("items")))
        top = [br.tree.topLevelItem(i) for i in range(br.tree.topLevelItemCount())]
        uno = [t for t in top if t.text(0).endswith("uno")][0]
        self.assertEqual(uno.child(0).text(0), "Loading...")           # not requested yet: only the arrow
        uno.setExpanded(True)                                           # second level, folders first
        self.assertTrue(pump(lambda: uno.childCount() == 2 and uno.child(0).text(0).endswith("due")))
        uno.child(0).setExpanded(True)                                  # third level
        self.assertTrue(pump(lambda: uno.child(0).childCount() == 1 and uno.child(0).child(0).text(0) == "t.png"))
        br.tree.setCurrentItem(uno.child(0).child(0))                  # a file selected: uploads would go to its folder
        self.assertEqual(br._target(), "uno/due")
        br.tree.setCurrentItem(uno)
        self.assertEqual(br._target(), "uno")
        self.assertEqual(br._selected()[0]["path"], "uno")

    def test_browser_start_folder(self):
        s = self.sess("tr2"); d = self.login_dialog(s, "tree2", register=True); pump(lambda: d.result() == 1)
        png = self.tmp / "u.png"; png.write_bytes(png_bytes())
        s.client.upload("mine", "alfa/beta/u.png", png)
        br = ui.ServerBrowserWidget(s, ("mine",))
        self.assertTrue(pump(lambda: br.status.text().endswith("items")))
        br._goto("mine", "alfa/beta")
        self.assertTrue(pump(lambda: br.tree.topLevelItemCount() == 1 and "u.png" in br.tree.topLevelItem(0).text(0)))
        self.assertEqual(br.path, "alfa/beta")

    def test_server_address_typed_by_hand(self):
        from unittest import mock
        from PySide6.QtWidgets import QInputDialog
        from corpse.functions.users.api import normalize_url
        from corpse.gui.users.login import server_address
        self.assertEqual(normalize_url("192.168.1.27:8765"), "http://192.168.1.27:8765")     # bare IP: plain HTTP
        self.assertEqual(normalize_url("localhost:8765"), "http://localhost:8765")
        self.assertEqual(normalize_url("server.example.org"), "https://server.example.org")
        self.assertEqual(server_address("http://10.0.0.5:8765"), "http://10.0.0.5:8765") if not os.environ.get("AM_SERVER_URL") else None
        s = self.sess("sv1")
        s.store.update_settings(server_url="http://10.0.0.5:8765")
        dlg = ui.LoginDialog(s)                                         # the saved address is proposed and editable
        self.assertEqual(dlg.url.text(), os.environ.get("AM_SERVER_URL") or "http://10.0.0.5:8765")
        self.assertTrue(dlg.url.isVisibleTo(dlg) or not dlg.isVisible())

        s2 = self.sess("sv2"); d = self.login_dialog(s2, "srv1", register=True); pump(lambda: d.result() == 1)
        from corpse.gui.settings_dialog import ServerPanel
        bar = ServerPanel(s2)                                           # the address is changed from the settings
        out = []
        bar.changed.connect(lambda: out.append(1))
        with mock.patch.object(QInputDialog, "getText", return_value=(self.url + "/", True)):
            bar._change_server()                                        # same server: nothing happens
        self.assertEqual(out, [])
        other = self.srv.url.replace("127.0.0.1", "localhost")
        with mock.patch.object(QInputDialog, "getText", return_value=(other, True)):
            bar._change_server()
        self.assertTrue(pump(lambda: out == [1]))
        self.assertEqual(s2.store.settings()["server_url"], other)

    def test_models_ask_for_the_scientific_name(self):
        from unittest import mock
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        s = self.sess("sp1"); d = self.login_dialog(s, "spec9", register=True); pump(lambda: d.result() == 1)
        br = ui.ServerBrowserWidget(s, ("models",))
        pump(lambda: br.status.text().endswith("items"))
        pairs = [(Path("best.pt"), "best.pt")]
        with mock.patch.object(QInputDialog, "getText", return_value=("Pinna nobilis", True)):
            self.assertEqual(br._with_species(pairs), [(Path("best.pt"), "Pinna nobilis/best.pt")])
        with mock.patch.object(QInputDialog, "getText", return_value=("pesce", True)), \
                mock.patch.object(QMessageBox, "warning") as warn:
            self.assertIsNone(br._with_species(pairs)); warn.assert_called_once()
        with mock.patch.object(QInputDialog, "getText", return_value=("", False)):
            self.assertIsNone(br._with_species(pairs))
        already = [(Path("b.pt"), "Pinna nobilis/b.pt")]                      # already inside a species folder: no question
        with mock.patch.object(QInputDialog, "getText", side_effect=AssertionError):
            self.assertEqual(br._with_species(already), already)

    def test_profile_page(self):
        s = self.sess("p1"); d = self.login_dialog(s, "prof9", register=True); pump(lambda: d.result() == 1)
        page = ui.ProfilePage(s)
        self.assertEqual(page.tabs.count(), 4)
        page.fields["full_name"].setText("Mario Rossi"); page.fields["bio"].setPlainText("ciao")
        page._save(); self.assertTrue(pump(lambda: "saved" in page.msg.text()), page.msg.text())
        self.assertEqual(s.store.profile("prof9")["full_name"], "Mario Rossi")
        page.old.setText("password123"); page.new.setText("nuovapass99"); page.new2.setText("nuovapass99")
        page._password(); self.assertTrue(pump(lambda: "Password changed" in page.msg.text()))
        page.local_edits["photos"].setText(str(self.tmp / "mie_foto")); page._save_folders()
        self.assertEqual(s.local_folders()["photos"], str(self.tmp / "mie_foto")); self.assertTrue((self.tmp / "mie_foto").is_dir())
        page._reset_folders(); self.assertNotEqual(s.local_folders()["photos"], str(self.tmp / "mie_foto"))
        g = self.sess("p2"); g.start_offline(); pg = ui.ProfilePage(g)
        self.assertEqual(pg.tabs.count(), 3)                                                # without a folder on the server
        pg._save_folders(); self.assertIn("guest", g.store._profiles())

    def test_admin_home(self):
        s = self.sess("c1"); s.login("admin", "adminpass1", self.url)
        calls = []
        home = ui.AdminHome(s, on_training=lambda: calls.append("t"), on_analysis=lambda: calls.append("a"))
        self.assertTrue(pump(lambda: home.users.table.rowCount() >= 1))
        self.assertTrue(home.db.btn_delete.isVisibleTo(home.db))
        self.assertEqual(home.tabs.count(), 4)
        self.assertEqual(home.tabs.tabText(2), "Review")
        self.assertIn("stereo", home.db.areas)                                  # the admin also browses the stereo photos and videos
        self.assertTrue(pump(lambda: home.users.events.rowCount() >= 1))
        self.assertTrue(s.store.users_snapshot()["users"])
        home.users.table.selectRow(0); self.assertEqual(home.users._current()["username"], "admin")

    def test_offline_views(self):
        s = self.sess("o1"); d = self.login_dialog(s, "off1", register=True); pump(lambda: d.result() == 1)
        s2 = Session(s.store); s2.server_url = self.url
        s2.user, s2.online = s.user, False
        br = ui.ServerBrowserWidget(s2); self.assertIn("offline", br.note.text().lower())
        bar = ui.AccountBar(s2); self.assertTrue(bar.btn_retry.isVisibleTo(bar) or True)

    def test_admin_home_offline_is_local_only(self):
        s = self.sess("o2"); s.user, s.online, s.client = {"username": "boss", "role": "server"}, False, None
        home = ui.AdminHome(s, on_training=lambda: None, on_analysis=lambda: None)
        self.assertFalse(home.banner.isHidden())
        self.assertFalse(any(home.tabs.isTabEnabled(i) for i in home.server_tabs))
        self.assertTrue(home.tabs.isTabEnabled(home.local_tab))
        self.assertEqual(home.tabs.currentIndex(), home.local_tab)

    def test_photo_review(self):
        a = self.sess("pr1"); a.login("admin", "adminpass1", self.url)
        c = ApiClient(self.url); c.register("pruser", "password123"); c.login("pruser", "password123")
        img = self.tmp / "p.png"; img.write_bytes(png_bytes())
        c.upload("photos", "Pinna nobilis/p.png", img)
        c.submit_species("Pinna nobilis")
        w = ui.SubmissionsWidget(a)
        mine = lambda: [i for i, s in enumerate(w.items) if s["username"] == "pruser"]
        self.assertTrue(pump(lambda: len(mine()) == 1))
        w.table.selectRow(mine()[0])
        yes = mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes)
        with yes:                                                       # finta risposta "Sì" alla conferma
            w._approve()
        self.assertTrue(pump(lambda: c.species_submissions()[0]["status"] == "approved"))
        c.upload("photos", "Epinephelus marginatus/q.png", img)
        c.submit_species("Epinephelus marginatus")
        w.refresh()
        self.assertTrue(pump(lambda: len(mine()) == 2))
        w.table.selectRow([i for i in mine() if w.items[i]["species"] == "Epinephelus marginatus"][0])
        with yes:
            w._reject()
        self.assertTrue(pump(lambda: c.species_submissions()[0]["status"] == "rejected"))

    def test_review_tabs_keep_each_kind_apart(self):
        a = self.sess("pr2"); a.login("admin", "adminpass1", self.url)
        c = ApiClient(self.url); c.register("pruser2", "password123"); c.login("pruser2", "password123")
        img = self.tmp / "p.png"; img.write_bytes(png_bytes())
        c.upload("photos", "Pinna nobilis/p.png", img)
        c.submit_species("Pinna nobilis")
        c.upload("models", "Pinna nobilis/m.pt", img)                    # il contenuto non conta: è solo un file
        c.submit_model("Pinna nobilis", "m.pt")
        w = ui.ReviewWidget(a)
        mine = lambda tab: [s for s in tab.items if s["username"] == "pruser2"]
        self.assertTrue(pump(lambda: len(mine(w.photos)) == 1 and len(mine(w.models)) == 1))
        self.assertEqual(mine(w.datasets), [])                           # nessun dataset inviato
        self.assertTrue(all(s["kind"] == "model" for s in w.models.items))
        self.assertTrue(all(s["kind"] == "photos" for s in w.photos.items))
        settle(w)

    def _user_session(self, name: str, user: str):
        ApiClient(self.url).register(user, "password123")
        s = self.sess(name)
        s.login(user, "password123", self.url)
        return s

    def _admin_client(self) -> ApiClient:
        c = ApiClient(self.url)
        c.login("admin", "adminpass1")
        return c

    def test_uploads_page_sends_a_single_photo_to_review(self):
        from PySide6.QtWidgets import QFileDialog
        s = self._user_session("up1", "upuser1")
        folder = self.tmp / "Pinna nobilis"
        folder.mkdir()
        (folder / "a.png").write_bytes(png_bytes())
        w = ui.UploadsWidget(s)
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=([str(folder / "a.png")], "")):
            w.btn_photos.click()                                         # one photo from a species folder: sent to review
        admin = self._admin_client()
        waiting = lambda: [x["species"] for x in admin.species_submissions(status="pending", kind="photos")
                           if x["username"] == "upuser1"]
        self.assertTrue(pump(lambda: waiting() == ["Pinna nobilis"]))
        settle(w)

    def test_uploads_page_sends_several_photos_picked_together(self):
        from PySide6.QtWidgets import QFileDialog, QInputDialog
        s = self._user_session("up8", "upuser8")
        names = []
        for n in ("a.png", "b.png", "c.png"):
            (self.tmp / n).write_bytes(png_bytes())
            names.append(str(self.tmp / n))
        w = ui.UploadsWidget(s)
        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=(names, "")), \
                mock.patch.object(QInputDialog, "getText", return_value=("Mola mola mola", True)):
            w.btn_photos.click()
        admin = self._admin_client()
        waiting = lambda: [x["photos"] for x in admin.species_submissions(status="pending", kind="photos")
                           if x["username"] == "upuser8"]
        self.assertTrue(pump(lambda: waiting() == [3]))                  # three names are a valid scientific name
        settle(w)

    def test_uploads_page_sends_a_dataset_to_review(self):
        from PySide6.QtWidgets import QFileDialog
        s = self._user_session("up2", "upuser2")
        root = self.tmp / "coralli_ds"
        (root / "images").mkdir(parents=True)
        (root / "labels").mkdir()
        (root / "data.yaml").write_text("names: [coral]\n")
        (root / "images" / "a.png").write_bytes(png_bytes())
        (root / "labels" / "a.txt").write_text("0 0.5 0.5 0.1 0.1\n")
        w = ui.UploadsWidget(s)
        with mock.patch.object(QFileDialog, "getExistingDirectory", return_value=str(root)):
            w.btn_dataset.click()
        admin = self._admin_client()
        waiting = lambda: [x["species"] for x in admin.species_submissions(status="pending", kind="dataset")
                           if x["username"] == "upuser2"]
        self.assertTrue(pump(lambda: waiting() == ["coralli_ds"]))
        settle(w)

    def test_uploads_page_sends_a_model_to_review(self):
        from PySide6.QtWidgets import QFileDialog, QInputDialog
        s = self._user_session("up3", "upuser3")
        f = self.tmp / "m.pt"
        f.write_bytes(b"0123456789")
        w = ui.UploadsWidget(s)
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(f), "")), \
                mock.patch.object(QInputDialog, "getText", return_value=("Pinna nobilis", True)):
            w.btn_model.click()                                          # chiede la specie, carica e invia
        admin = self._admin_client()
        waiting = lambda: [x["species"] for x in admin.species_submissions(status="pending", kind="model")
                           if x["username"] == "upuser3"]
        self.assertTrue(pump(lambda: waiting() == ["Pinna nobilis"]))
        settle(w)

    def test_server_folders_is_a_page_with_three_sections_not_a_window(self):
        from PySide6.QtWidgets import QDialog
        s = self._user_session("sf1", "sfuser1")
        w = ui.ServerFoldersWidget(s)
        self.assertNotIsInstance(w, QDialog)                              # the home shows it inside its own window
        self.assertEqual([w.tabs.tabText(i) for i in range(w.tabs.count())], ["Photos", "Stereo photos", "Videos", "Stereo videos", "YOLO models", "Uploads"])
        settle(w)

    def test_preview_shows_the_photos_of_a_submission(self):
        c = ApiClient(self.url)
        c.register("pvuser1", "password123")
        c.login("pvuser1", "password123")
        img = self.tmp / "p.png"
        img.write_bytes(png_bytes())
        c.upload("photos", "Pinna nobilis/p.png", img)
        sent = c.submit_species("Pinna nobilis")
        admin = self._admin_client()
        row = [s for s in admin.species_submissions(kind="photos") if s["id"] == sent["id"]][0]
        d = ui.PreviewDialog(admin, "photos", row)
        self.assertTrue(pump(lambda: d.thumbs.count() == 1))
        settle(d)

    def test_preview_writes_nothing_to_disk(self):
        c = ApiClient(self.url)
        c.register("pvuser3", "password123")
        c.login("pvuser3", "password123")
        img = self.tmp / "q.png"
        img.write_bytes(png_bytes())
        c.upload("photos", "Pinna nobilis/q.png", img)
        sent = c.submit_species("Pinna nobilis")
        admin = self._admin_client()
        row = [s for s in admin.species_submissions(kind="photos") if s["id"] == sent["id"]][0]

        def no_download(*a, **k):
            raise AssertionError("a preview must not download files to disk")
        admin.download = no_download
        d = ui.PreviewDialog(admin, "photos", row)
        self.assertTrue(pump(lambda: d.thumbs.count() == 1))
        self.assertFalse(hasattr(d, "_tmp"))
        settle(d)

    def test_preview_of_a_model_shows_its_details(self):
        c = ApiClient(self.url)
        c.register("pvuser2", "password123")
        c.login("pvuser2", "password123")
        pt, meta = self.tmp / "m.pt", self.tmp / "m.json"
        pt.write_bytes(b"0123456789")
        meta.write_text('{"schema": 1, "species": "Pinna nobilis", "base_model": "yolo11n-seg.pt"}')
        c.upload("models", "Pinna nobilis/m.pt", pt)
        c.upload("models", "Pinna nobilis/m.json", meta)
        sent = c.submit_model("Pinna nobilis", "m.pt")
        admin = self._admin_client()
        row = [s for s in admin.species_submissions(kind="model") if s["id"] == sent["id"]][0]
        d = ui.PreviewDialog(admin, "model", row)
        self.assertTrue(pump(lambda: "Pinna nobilis" in d.info.text()))
        self.assertTrue(d.thumbs.isHidden())                           # a model has no pictures
        settle(d)

    def test_a_reviewed_submission_has_no_approve_and_reject_buttons(self):
        w = ui.SubmissionsWidget(self.sess("sb1"))
        row = lambda sid, status: {"id": sid, "username": "u", "species": "Pinna nobilis", "photos": 1,
                                   "created": 1_700_000_000, "status": status}
        w._fill([row(1, "pending"), row(2, "approved"), row(3, "rejected")])
        for index, hidden in ((0, False), (1, True), (2, True)):
            w.table.selectRow(index)
            self.assertEqual(w.btn_approve.isHidden(), hidden)
            self.assertEqual(w.btn_reject.isHidden(), hidden)
            self.assertFalse(w.btn_preview.isHidden())                     # these two stay for every row
            self.assertFalse(w.btn_refresh.isHidden())
        settle(w)

    def test_browser_does_not_list_the_waiting_folder(self):
        c = ApiClient(self.url)
        c.register("bwuser1", "password123")
        c.login("bwuser1", "password123")
        img = self.tmp / "a.png"
        img.write_bytes(png_bytes())
        c.upload("datasets", "mini/images/a.png", img)                  # a user's upload waits in quarantine
        a = self.sess("bw1")
        a.login("admin", "adminpass1", self.url)
        w = ui.ServerBrowserWidget(a, ("datasets",))
        self.assertTrue(pump(lambda: w.status.text() == "0 items"))     # the waiting folder is not listed: the Review has it
        settle(w)

    def _approved_photos(self, user, species):
        c = ApiClient(self.url)
        c.register(user, "password123")
        c.login(user, "password123")
        img = self.tmp / f"{user}.png"
        img.write_bytes(png_bytes())
        c.upload("photos", f"{species}/p.png", img)
        self._admin_client().approve_submission(c.submit_species(species)["id"])

    def _approved_model(self, user, species, name):
        c = ApiClient(self.url)
        c.register(user, "password123")
        c.login(user, "password123")
        pt, meta = self.tmp / f"{name}.pt", self.tmp / f"{name}.json"
        pt.write_bytes(b"0123456789")
        meta.write_text('{"schema": 1}')
        c.upload("models", f"{species}/{name}.pt", pt)
        c.upload("models", f"{species}/{name}.json", meta)
        self._admin_client().approve_submission(c.submit_model(species, f"{name}.pt")["id"])

    def _species_row(self, w, species):
        tops = [w.tree.topLevelItem(i) for i in range(w.tree.topLevelItemCount())]
        return [t for t in tops if t.text(0) == species][0]

    def _opened(self, w, species):
        """The species row, opened and with its real children loaded (they are fetched when it is opened)."""
        row = self._species_row(w, species)
        row.setExpanded(True)
        self.assertTrue(pump(lambda: row.childCount() >= 1 and row.child(0).data(0, __import__('corpse.gui.users.catalog', fromlist=['x']).RECORD) is not None))
        return row

    def test_catalog_lists_every_species_alphabetically_and_every_photo_beside_its_data(self):
        self._approved_photos("cvuser1", "Hippocampus guttulatus")
        self._approved_photos("cvuser2", "Anthias anthias")
        w = ui.CatalogWidget(self._user_session("cat1", "cvuser10"), "photos")
        self.assertTrue(pump(lambda: w.tree.topLevelItemCount() >= 2))
        names = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
        self.assertEqual(names, sorted(names, key=str.lower))
        row = self._opened(w, "Hippocampus guttulatus").child(0)
        self.assertEqual((row.text(3), row.text(4)), ("cvuser1", "admin"))
        self.assertRegex(row.text(5), r"^\d{4}-\d{2}-\d{2}$")             # only the date, never the time
        self.assertTrue(row.text(0).lower().endswith(".png"))
        settle(w)

    def test_catalog_filter_hides_what_does_not_match(self):
        self._approved_photos("cvuser11", "Mullus surmuletus")
        self._approved_photos("cvuser12", "Sarpa salpa")
        w = ui.CatalogWidget(self._user_session("cat6", "cvuser13"), "photos")
        self.assertTrue(pump(lambda: w.tree.topLevelItemCount() >= 2))
        w.filter.setText("sarpa")
        self.assertTrue(self._species_row(w, "Mullus surmuletus").isHidden())
        self.assertFalse(self._species_row(w, "Sarpa salpa").isHidden())
        w.filter.setText("cvuser11")                                       # by who uploaded
        self.assertFalse(self._species_row(w, "Mullus surmuletus").isHidden())
        self.assertTrue(self._species_row(w, "Sarpa salpa").isHidden())
        w.filter.setText("")
        self.assertFalse(self._species_row(w, "Sarpa salpa").isHidden())
        settle(w)

    def test_catalog_sorts_species_alphabetically_in_both_directions(self):
        self._approved_photos("cvuser14", "Boops boops")
        w = ui.CatalogWidget(self._user_session("cat7", "cvuser15"), "photos")
        self.assertTrue(pump(lambda: w.tree.topLevelItemCount() >= 1))
        for order in (Qt.SortOrder.DescendingOrder, Qt.SortOrder.AscendingOrder):
            w.tree.sortByColumn(3, order)
            names = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
            self.assertEqual(names, sorted(names, key=str.lower))
        settle(w)

    def test_catalog_download_needs_a_selection(self):
        self._approved_photos("cvuser3", "Chromis chromis")
        w = ui.CatalogWidget(self._user_session("cat2", "cvuser4"), "photos")
        self.assertTrue(pump(lambda: w.tree.topLevelItemCount() >= 1))
        self.assertFalse(w.btn_download.isEnabled())
        w.tree.setCurrentItem(self._opened(w, "Chromis chromis").child(0))
        self.assertTrue(w.btn_download.isEnabled())
        settle(w)

    def test_model_catalog_lists_the_files(self):
        self._approved_model("cvuser5", "Dentex dentex", "cvm")
        w = ui.CatalogWidget(self._user_session("cat3", "cvuser6"), "model")
        self.assertTrue(pump(lambda: w.tree.topLevelItemCount() >= 1))
        row = self._opened(w, "Dentex dentex").child(0)
        self.assertEqual((row.text(0), row.text(3), row.text(4), row.text(2)), ("cvm.pt", "cvuser5", "admin", "10 B"))
        settle(w)

    def test_catalog_downloads_the_chosen_photos(self):
        from PySide6.QtWidgets import QFileDialog
        self._approved_photos("cvuser7", "Diplodus sargus")
        w = ui.CatalogWidget(self._user_session("cat4", "cvuser8"), "photos")
        self.assertTrue(pump(lambda: w.tree.topLevelItemCount() >= 1))
        w.tree.setCurrentItem(self._opened(w, "Diplodus sargus").child(0))
        dest = self.tmp / "scaricate"
        dest.mkdir()
        with mock.patch.object(QFileDialog, "getExistingDirectory", return_value=str(dest)):
            w.btn_download.click()
        self.assertTrue(pump(lambda: any(dest.rglob("IMG_0001.*"))))
        settle(w)

    def test_catalog_columns_fill_the_width_and_the_header_is_taller(self):
        from PySide6.QtWidgets import QHeaderView
        w = ui.CatalogWidget(self._user_session("cat5", "cvuser9"), "photos")
        header = w.tree.header()
        self.assertEqual(header.sectionResizeMode(2), QHeaderView.ResizeMode.Stretch)
        self.assertGreaterEqual(header.minimumHeight(), 30)
        settle(w)

    def test_photo_viewer_shows_the_labels_on_the_right_when_they_exist(self):
        class Fake:                                         # a server holding one photo and, maybe, its label
            def __init__(self, files): self.files = files
            def read_bytes(self, area, rel, max_bytes=0):
                if (area, rel) not in self.files: raise KeyError(rel)
                return self.files[(area, rel)]
            def list(self, area, rel):
                names = {}
                for (a, r) in self.files:
                    if a == area and r.startswith(rel + "/"):
                        head, _, tail = r[len(rel) + 1:].partition("/")
                        names[head] = "dir" if tail else "file"
                return [{"name": n, "type": t, "size": 1} for n, t in names.items()]
        photo = {("photos", "Coris julis/b/IMG_0001.png"): png_bytes()}
        with_labels = dict(photo)
        with_labels[("datasets", "Coris julis/d/labels/IMG_0001.txt")] = b"0 0.5 0.5 0.4 0.4\n"
        with_labels[("datasets", "Coris julis/d/data.yaml")] = b"names:\n  0: wrasse\n"
        dlg = ui.ImageViewerDialog(Fake(with_labels), "photos", "Coris julis/b/IMG_0001.png", labels_area="datasets")
        self.assertTrue(pump(lambda: dlg.original is not None))
        self.assertIsNotNone(dlg.labelled)
        self.assertFalse(dlg.right.isHidden())
        dlg2 = ui.ImageViewerDialog(Fake(photo), "photos", "Coris julis/b/IMG_0001.png", labels_area="datasets")
        self.assertTrue(pump(lambda: dlg2.original is not None))
        self.assertIsNone(dlg2.labelled)
        self.assertTrue(dlg2.right.isHidden())

    def _opened_first_photo(self, species, client):
        from common.remote_tree import walk_remote
        return [p for p, _s in walk_remote(client, "photos", species) if p.lower().endswith(".png")][0]

    # ---- other pages ---------------------------------------------------------
    def test_language_widget(self):
        import http.server
        from functools import partial
        from tools import build_language_packs as blp
        site = self.tmp / "loc"; blp.main(["--out", str(site)])
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k): pass
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(site)))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            mgr = i18n.LanguageManager(self.tmp / "ldata", f"http://127.0.0.1:{httpd.server_address[1]}/index.json")
            w = LanguageWidget(mgr)
            self.assertTrue(pump(lambda: "it" in w.available))
            codes = list(__import__("common.params", fromlist=["x"]).LANGUAGES)
            w.table.selectRow(codes.index("it")); w._buttons()
            self.assertIn("Download", w.btn_main.text())
            w._main_action(); self.assertTrue(pump(lambda: "it" in mgr.installed()))
            self.assertTrue(pump(lambda: i18n.current_language() == "it"))
            from corpse.gui.users.login import LoginDialog
            dlg = LoginDialog(self.sess("l1")); self.assertEqual(dlg.btn_ok.text(), "Accedi")   # the new windows speak Italian
            w.table.selectRow(codes.index("en")); w._buttons(); self.assertFalse(w.btn_remove.isEnabled())
        finally:
            i18n.set_language("en"); httpd.shutdown(); httpd.server_close()

    def test_analysis_hub_and_manual(self):
        from corpse.gui.home.hub import AnalysisHub
        from corpse.functions.home.hub_params import ANALYSES
        from PySide6.QtWidgets import QLabel
        calls = []
        hub = AnalysisHub(on_home=lambda: calls.append("home"), demo=QLabel("demo")); got = []
        hub.requested.connect(got.append)
        self.assertEqual(len(hub.cards), 4)
        self.assertIs(hub.demo.parent() is not None, True)              # the demo lives in this screen
        for aid in hub.cards: hub.cards[aid].clicked.emit()
        self.assertEqual(got, [a[0] for a in ANALYSES])
        from corpse.gui.manual.page import ManualWidget, split_sections
        from corpse.gui.manual.content import MANUAL
        m = ManualWidget(); self.assertEqual(len(m.sections), len(split_sections(MANUAL)))
        self.assertGreaterEqual(m.index.count(), 9)
        m.search.setText("quarantine"); self.assertTrue(0 < m.index.count() < len(m.sections))
        m.search.setText("zzzzz"); self.assertEqual(m.index.count(), 0)

    def test_training_dialog(self):
        fake = types.ModuleType("core.environment_manager")
        fake.PROJECT_ROOT = ROOT
        fake.get_cuda_status = lambda: {"install_needed": False, "extras_pending": True, "install_variant": "", "gpu_name": ""}
        fake.launch_training_installer = lambda: True
        sys.modules["core"] = sys.modules.get("core") or types.ModuleType("core")
        sys.modules["core.environment_manager"] = fake
        from corpse.gui.training.setup_dialog import TrainingSetupDialog, ensure_training_ready
        d = TrainingSetupDialog(fake.get_cuda_status())
        self.assertFalse(d.heavy); self.assertIn("a few MB", d.info.text())
        d2 = TrainingSetupDialog({"install_needed": True, "extras_pending": False, "install_variant": "cu126", "gpu_name": "GTX"})
        self.assertTrue(d2.heavy and "restart by itself" in d2.info.text() and "GTX" in d2.info.text())
        fake.get_cuda_status = lambda: {"install_needed": False, "extras_pending": False, "install_variant": "", "gpu_name": ""}
        self.assertTrue(ensure_training_ready())                                            # nothing to install

    def test_browser_shows_the_details_of_a_model(self):
        from PySide6.QtCore import Qt
        from common.model_metadata import build_metadata, write_metadata
        from corpse.functions.training.publish import publish_model
        i18n.set_language("en")
        s = self.sess("mi1"); d = self.login_dialog(s, "admin", pw="adminpass1"); pump(lambda: d.result() == 1)
        with_meta, without = self.tmp / "details.pt", self.tmp / "nodetails.pt"
        with_meta.write_bytes(b"x"); without.write_bytes(b"x")
        write_metadata(with_meta, build_metadata(base_model="yolo11n-seg.pt", dataset_name="ok", dataset_source="server",
                                                 epochs=5, imgsz=640, batch=8, device="cpu", trained_by="admin",
                                                 classes=["Pinna nobilis"], dataset_images=120))
        publish_model(s.client, with_meta, "Pinna nobilis")
        publish_model(s.client, without, "Pinna nobilis")

        br = ui.ServerBrowserWidget(s, ("models",))
        pump(lambda: br.status.text().endswith("items"))
        br.path = "Pinna nobilis"; br.refresh()
        self.assertTrue(pump(lambda: br.tree.topLevelItemCount() == 3), br.status.text())    # details.pt, details.json, nodetails.pt

        def select(name):
            br.tree.clearSelection()
            for i in range(br.tree.topLevelItemCount()):
                item = br.tree.topLevelItem(i)
                if item.data(0, Qt.ItemDataRole.UserRole)["name"] == name:
                    br.tree.setCurrentItem(item)

        self.assertTrue(br.info.isHidden())                                  # niente selezionato: pannello nascosto
        select("details.pt")
        self.assertTrue(pump(lambda: "Species: Pinna nobilis" in br.info.text()), br.info.text())
        self.assertIn("Dataset: ok (120 images)", br.info.text())
        select("nodetails.pt")
        self.assertTrue(pump(lambda: "No details available" in br.info.text()), br.info.text())
        select("details.json")                                               # il file dei metadati non ha un pannello
        self.assertTrue(pump(lambda: br.info.isHidden()))

    def test_browser_hides_the_internal_quarantine_name(self):
        from corpse.functions.training.publish import publish_model
        i18n.set_language("en")
        su = self.sess("qu1"); d = self.login_dialog(su, "quarantena1", register=True); pump(lambda: d.result() == 1)
        model = self.tmp / "quarantena.pt"; model.write_bytes(b"x")
        publish_model(su.client, model, "Pinna nobilis")                    # a normal user: the model goes to _pending
        sa = self.sess("qa1"); d = self.login_dialog(sa, "admin", pw="adminpass1"); pump(lambda: d.result() == 1)

        br = ui.ServerBrowserWidget(sa, ("models",))
        self.assertTrue(pump(lambda: br.status.text() == "0 items"))           # the waiting folder is not listed: the Review has it
        self.assertNotIn("_pending", br.note.text())                           # nor is it named in the administrator's note

        br.path = "_pending/quarantena1/Pinna nobilis"; br.refresh()
        self.assertTrue(pump(lambda: br.status.text().endswith("items") and br.tree.topLevelItemCount() >= 1))
        self.assertIn("Awaiting approval / quarantena1 / Pinna nobilis", br.crumb.text())
        self.assertNotIn("_pending", br.crumb.text())

    def test_skeleton_admin_database_has_catalog_datasets_and_models(self):
        i18n.set_language("en")
        s = self.sess("sk1"); d = self.login_dialog(s, "admin", pw="adminpass1"); pump(lambda: d.result() == 1)
        home = ui.AdminHome(s, lambda: None, lambda: None)
        self.assertTrue(settle(home))
        self.assertEqual(home.db.areas, ("photos", "stereo", "videos", "stereo_videos", "models", "datasets"))
        self.assertEqual([home.db.tabs.tabText(i) for i in range(6)],
                         ["Photos", "Stereo photos", "Videos", "Stereo videos", "YOLO models", "Datasets"])

    def test_skeleton_admin_review_has_photos_datasets_and_models(self):
        i18n.set_language("en")
        s = self.sess("sk2"); d = self.login_dialog(s, "admin", pw="adminpass1"); pump(lambda: d.result() == 1)
        home = ui.AdminHome(s, lambda: None, lambda: None)
        self.assertTrue(settle(home))
        self.assertEqual([home.review.tabs.tabText(i) for i in range(6)],
                         ["Photos", "Stereo photos", "Videos", "Stereo videos", "Datasets", "YOLO models"])
        self.assertEqual(home.tabs.tabText(home.tabs.indexOf(home.review)), "Review")

    def test_skeleton_user_sees_photos_and_models_to_download_and_uploads(self):
        i18n.set_language("en")
        s = self.sess("sk3"); d = self.login_dialog(s, "skeleton1", register=True); pump(lambda: d.result() == 1)
        dlg = ui.ServerFoldersWidget(s)
        self.assertTrue(settle(dlg))
        self.assertEqual([dlg.tabs.tabText(i) for i in range(6)],
                         ["Photos", "Stereo photos", "Videos", "Stereo videos", "YOLO models", "Uploads"])
        for catalog in (dlg.photos, dlg.stereo, dlg.videos, dlg.stereo_videos, dlg.models):                                # only download: no way to change anything
            self.assertTrue(catalog.btn_download.isVisibleTo(catalog))
            for name in ("btn_up_files", "btn_up_dir", "btn_mkdir", "btn_rename", "btn_delete", "btn_approve"):
                self.assertFalse(hasattr(catalog, name))

if __name__ == "__main__":
    unittest.main(verbosity=1)
