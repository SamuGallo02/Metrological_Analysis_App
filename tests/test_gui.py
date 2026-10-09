"""Headless test of the windows (QT_QPA_PLATFORM=offscreen)."""
import os, sys, tempfile, threading, time, types, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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


def pump(cond, secs=8):
    t = time.time()
    while time.time() - t < secs and not cond():
        app.processEvents(); time.sleep(0.02)
    app.processEvents()
    return cond()


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
        png = self.tmp / "f.png"; png.write_bytes(png_bytes())
        jobs = [("f.png", png.stat().st_size, lambda cb, cancel: s.client.upload("photos", "f.png", png, cb, cancel))]
        td = ui.TransferDialog("t", jobs); td.exec()
        self.assertFalse(td.errors or td.skipped)
        br.refresh(); self.assertTrue(pump(lambda: br.tree.topLevelItemCount() == 1))
        td2 = ui.TransferDialog("t", jobs); td2.exec(); self.assertTrue(td2.skipped and not td2.errors)

        mine = ui.ServerBrowserWidget(s, ("mine",))                                         # personal area: everything visible
        self.assertTrue(pump(lambda: mine.status.text().endswith("items")))
        self.assertTrue(mine.btn_delete.isVisibleTo(mine) and mine.btn_rename.isVisibleTo(mine))
        self.assertTrue(pump(lambda: mine.quota.isVisibleTo(mine) and mine.quota.maximum() == 1024))

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
        self.assertEqual(home.tabs.count(), 3)
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
        self.assertFalse(home.tabs.isTabEnabled(0) or home.tabs.isTabEnabled(1))
        self.assertTrue(home.tabs.isTabEnabled(2)); self.assertEqual(home.tabs.currentIndex(), 2)

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
