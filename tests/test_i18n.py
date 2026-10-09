import http.server, json, os, sys, tempfile, threading, unittest
from functools import partial
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import i18n
from common.errors import AppError
from common.params import LANGUAGES
from tools import build_language_packs as blp
from tools.extract_strings import extract


class TestI18n(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.site = Path(cls.tmp.name) / "locales"
        assert blp.main(["--out", str(cls.site)]) == 0
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k): pass
        handler = partial(Quiet, directory=str(cls.site))
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.index = f"http://127.0.0.1:{cls.httpd.server_address[1]}/index.json"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close(); cls.tmp.cleanup(); i18n.set_language("en")

    def setUp(self):
        i18n.set_language("en")

    def test_all_languages_complete(self):
        keys, bad = extract()
        self.assertFalse(bad)
        for code in LANGUAGES:
            if code == "en": continue
            m = blp.load(code)
            self.assertEqual(blp.problems_for(code, m.STRINGS, m.MANUAL, keys), [], code)

    def test_english_is_identity_and_formats(self):
        self.assertEqual(i18n.tr("Sign in"), "Sign in")
        self.assertEqual(i18n.tr("{n} items", n=3), "3 items")
        self.assertEqual(i18n.tr("never translated {x}", x=1), "never translated 1")

    def test_download_install_activate_remove(self):
        folder = Path(self.tmp.name) / "user"
        mgr = i18n.LanguageManager(folder, self.index)
        self.assertEqual(mgr.installed(), ["en"])
        entries = {e["code"]: e for e in mgr.fetch_index()}
        self.assertEqual(set(entries), {"it", "es", "de", "fr", "zh", "ja"})
        seen = []
        mgr.install(entries["it"], lambda d, t: seen.append((d, t)))
        self.assertTrue(seen and seen[-1][0] == seen[-1][1])
        self.assertEqual(mgr.installed(), ["en", "it"]); self.assertEqual(mgr.installed_version("it"), entries["it"]["version"])
        self.assertTrue(mgr.activate("it"))
        self.assertEqual(i18n.tr("Sign in"), "Accedi"); self.assertEqual(i18n.tr("{n} items", n=2), "2 elementi")
        self.assertEqual(i18n.tr("English only text"), "English only text")          # senza traduzione: inglese
        self.assertIn("Manuale", i18n.current_manual())
        self.assertEqual(i18n.tr_error(AppError("The password must be at least {n} characters long.", n=8)),
                         "La password deve contenere almeno 8 caratteri.")
        # riavvio dell'app: la lingua salvata torna attiva
        i18n.set_language("en"); self.assertEqual(i18n.init_language(folder), "it"); self.assertEqual(i18n.tr("Sign in"), "Accedi")
        mgr.remove("it")
        self.assertEqual(i18n.current_language(), "en"); self.assertEqual(mgr.installed(), ["en"])
        self.assertEqual(i18n.init_language(folder), "en")

    def test_corrupted_download_rejected_and_unknown_language(self):
        folder = Path(self.tmp.name) / "user2"
        mgr = i18n.LanguageManager(folder, self.index)
        e = dict(next(x for x in mgr.fetch_index() if x["code"] == "de")); e["sha256"] = "0" * 64
        with self.assertRaises(ValueError): mgr.install(e)
        self.assertEqual(mgr.installed(), ["en"])
        self.assertFalse(i18n.set_language("xx", folder)); self.assertFalse(i18n.set_language("fr", folder))

    def test_every_language_installs_and_translates_ui(self):
        mgr = i18n.LanguageManager(Path(self.tmp.name) / "user3", self.index)
        for e in mgr.fetch_index():
            mgr.install(e); self.assertTrue(mgr.activate(e["code"]))
            self.assertNotEqual(i18n.tr("Sign in"), "Sign in", e["code"])
            self.assertGreater(len(i18n.current_manual()), 800)
        i18n.set_language("en")


if __name__ == "__main__":
    unittest.main()
