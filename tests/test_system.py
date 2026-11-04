import os, sys, threading, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.params import ROLE_SERVER
from server import config
from server.app import make_server
from server.db import Database
from corpse.functions.users.api import ApiClient, ApiError, Cancelled, OfflineError
from corpse.functions.users.session import Session
from corpse.functions.users.store import LocalStore
from tests.util import KEY, TestServer, png_bytes


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = TestServer()
        cls.url, cls.data, cls.tmp = cls.srv.url, cls.srv.data, cls.srv.tmp
        cls.work = Path(cls.tmp.name) / "work"
        cls.work.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def setUp(self):
        th = self.srv.httpd.handler.key_throttle
        th.reset(*list(th._d))

    def admin(self):
        c = ApiClient(self.url); c.login("admin", "adminpass1"); return c

    def user(self, name="mario"):
        c = ApiClient(self.url)
        try: c.register(name, "password123")
        except ApiError: pass
        c.login(name, "password123"); return c

    def f(self, name, data):
        p = self.work / name; p.write_bytes(data); return p


class TestAccounts(Base):
    def test_register_login_roles(self):
        self.assertEqual(self.user("anna").me()["role"], "user")
        self.assertEqual(self.admin().me()["role"], "server")
        with self.assertRaises(ApiError) as e: ApiClient(self.url).login("anna", "sbagliata")
        self.assertEqual(e.exception.status, 401)

    def test_register_cannot_choose_role(self):
        c = ApiClient(self.url)
        c._request("POST", "/api/register", body={"username": "furbo", "password": "password123", "role": "server"})
        c.login("furbo", "password123"); self.assertEqual(c.me()["role"], "user")

    def test_validation(self):
        with self.assertRaises(ApiError): ApiClient(self.url).register("a b", "password123")
        with self.assertRaises(ApiError) as e: ApiClient(self.url).register("okname", "corta")
        self.assertEqual(e.exception.params, {"n": 8})

    def test_unauthenticated(self):
        with self.assertRaises(ApiError) as e: ApiClient(self.url).list("photos")
        self.assertEqual(e.exception.status, 401)

    def test_password_lockout(self):
        self.user("lock")
        for _ in range(5):
            with self.assertRaises(ApiError): ApiClient(self.url).login("lock", "x")
        with self.assertRaises(ApiError) as e: ApiClient(self.url).login("lock", "password123")
        self.assertEqual(e.exception.status, 429); self.assertGreater(e.exception.retry_after, 200)

    def test_users_admin_only(self):
        u = self.user("bob")
        with self.assertRaises(ApiError) as e: u.users()
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(ApiError): u.create_user("x1234", "password123", "server")
        self.assertIn("bob", [x["username"] for x in self.admin().users()])

    def test_admin_manage_users(self):
        a = self.admin(); u = a.create_user("carla", "password123", "user")
        self.assertEqual(a.update_user(u["id"], role="server")["role"], "server")
        a.update_user(u["id"], active=False)
        with self.assertRaises(ApiError): ApiClient(self.url).login("carla", "password123")
        a.update_user(u["id"], active=True, password="nuovapass99")
        ApiClient(self.url).login("carla", "nuovapass99")
        a.delete_user(u["id"]); self.assertNotIn("carla", [x["username"] for x in a.users()])

    def test_last_admin_protected(self):
        a = self.admin(); me = a.me()
        with self.assertRaises(ApiError): a.update_user(me["id"], role="user")
        with self.assertRaises(ApiError): a.delete_user(me["id"])

    def test_deactivate_revokes_token(self):
        a = self.admin(); u = self.user("tokk"); uid = u.me()["id"]
        a.update_user(uid, active=False)
        with self.assertRaises(ApiError) as e: u.me()
        self.assertEqual(e.exception.status, 401)

    def test_change_password(self):
        c = self.user("pwchg"); c.change_password("password123", "altrapass456")
        ApiClient(self.url).login("pwchg", "altrapass456")


class TestAdminKey(Base):
    def test_register_with_key_is_admin(self):
        c = ApiClient(self.url); c.register("capo1", "password123", KEY); c.login("capo1", "password123")
        self.assertEqual(c.me()["role"], "server"); self.assertTrue(c.users())

    def test_wrong_key_does_not_create_account(self):
        with self.assertRaises(ApiError) as e: ApiClient(self.url).register("nokey1", "password123", "sbagliata")
        self.assertEqual(e.exception.status, 403)
        self.assertNotIn("nokey1", [u["username"] for u in self.admin().users()])

    def test_login_with_key_makes_admin_permanently(self):
        self.user("perm1")
        u = ApiClient(self.url).login("perm1", "password123", KEY)
        self.assertEqual(u["role"], "server")
        plain = ApiClient(self.url); plain.login("perm1", "password123")        # without a key: stays administrator
        self.assertEqual(plain.me()["role"], "server"); self.assertTrue(plain.users())
        self.assertEqual([x["role"] for x in self.admin().users() if x["username"] == "perm1"], ["server"])
        self.assertTrue(any(e["action"] == "promote.admin_key" for e in self.admin().events()))

    def test_wrong_key_on_login_no_session_no_promotion(self):
        self.user("perm2")
        with self.assertRaises(ApiError) as e: ApiClient(self.url).login("perm2", "password123", "xxxx")
        self.assertEqual(e.exception.status, 403)
        c = ApiClient(self.url); c.login("perm2", "password123"); self.assertEqual(c.me()["role"], "user")

    def test_key_not_checked_with_wrong_password(self):
        self.user("perm3")
        with self.assertRaises(ApiError) as e: ApiClient(self.url).login("perm3", "sbagliata1", KEY)
        self.assertEqual(e.exception.status, 401)

    def test_five_wrong_keys_block_key_for_five_minutes_but_not_server(self):
        self.user("brute0")
        codes = []
        for _ in range(7):
            try: ApiClient(self.url).login("brute0", "password123", "nope")
            except ApiError as e: codes.append((e.status, e.retry_after))
        self.assertEqual([c[0] for c in codes], [403] * 5 + [429, 429])
        self.assertTrue(290 <= codes[5][1] <= 301, codes[5])
        # even the correct key is rejected during the pause, and does not promote
        with self.assertRaises(ApiError) as e: ApiClient(self.url).login("brute0", "password123", KEY)
        self.assertEqual(e.exception.status, 429)
        with self.assertRaises(ApiError) as e: ApiClient(self.url).register("brute9", "password123", KEY)
        self.assertEqual(e.exception.status, 429)
        # ...but the server is NOT blocked: health, normal login, files, other users
        self.assertTrue(ApiClient(self.url).health()["ok"])
        c = ApiClient(self.url); c.login("brute0", "password123"); self.assertEqual(c.me()["role"], "user")
        ApiClient(self.url).register("normale1", "password123")
        self.assertTrue(self.admin().users())
        # after 5 minutes the key can be used again
        for k, (n, until) in list(self.srv.httpd.handler.key_throttle._d.items()):
            self.srv.httpd.handler.key_throttle._d[k] = (n, time.time() - 1)
        self.assertEqual(ApiClient(self.url).login("brute0", "password123", KEY)["role"], "server")

    def test_key_lockout_is_per_ip_when_proxied(self):
        s = TestServer(trust_proxy=True)
        try:
            from http.client import HTTPConnection
            def post(name, key, ip):
                conn = HTTPConnection("127.0.0.1", int(s.url.rsplit(":", 1)[1]))
                conn.request("POST", "/api/register", json.dumps({"username": name, "password": "password123", "key": key}),
                             {"Content-Type": "application/json", "X-Forwarded-For": "6.6.6.6, " + ip})
                r = conn.getresponse(); r.read(); conn.close(); return r.status
            import json
            for _ in range(5): post("zz1234", "bad", "1.1.1.1")
            self.assertEqual(post("zz1234", "bad", "1.1.1.1"), 429)
            self.assertEqual(post("zz5678", "bad", "2.2.2.2"), 403)         # other IP: not blocked
        finally:
            s.close()

    def test_key_disabled(self):
        s = TestServer(admin_key="")
        try:
            with self.assertRaises(ApiError) as e: ApiClient(s.url).register("zz1234", "password123", KEY)
            self.assertEqual(e.exception.status, 403)
            self.assertFalse(ApiClient(s.url).health()["key"])
        finally:
            s.close()

    def test_key_is_not_in_the_source_code(self):
        root = Path(__file__).resolve().parent.parent
        for pkg in ("server", "common", "corpse"):
            for p in (root / pkg).rglob("*.py"):
                self.assertNotIn("abcd", p.read_text(encoding="utf-8"), p)
        key_file = root / "server" / "admin_key.txt"                  # git-ignored: absent on a fresh clone / in CI
        if key_file.exists():
            self.assertEqual(key_file.read_text().strip(), "abcd")

    def test_key_loading_and_hash(self):
        with self.subTest("env"):
            os.environ["AM_ADMIN_KEY"] = " envkey "
            try: self.assertEqual(config.load_admin_key(self.data), "envkey")
            finally: del os.environ["AM_ADMIN_KEY"]
        with self.subTest("hash"):
            h = config.hash_key("segreta-lunga")
            self.assertTrue(config.key_matches("segreta-lunga", h)); self.assertFalse(config.key_matches("altra", h))
            self.assertFalse(config.key_matches("", h)); self.assertFalse(config.key_matches("x", ""))
        with self.subTest("server with hashed key"):
            s = TestServer(admin_key=config.hash_key("segreta-lunga"))
            try:
                c = ApiClient(s.url); c.register("hh1234", "password123", "segreta-lunga"); c.login("hh1234", "password123")
                self.assertEqual(c.me()["role"], "server")
            finally: s.close()


class TestProfile(Base):
    def test_profile_roundtrip_and_validation(self):
        c = self.user("prof1")
        u = c.update_profile(full_name="Mario Rossi", email="m@r.it", organization="UNIPD", bio="ciao")
        self.assertEqual((u["full_name"], u["email"], u["organization"]), ("Mario Rossi", "m@r.it", "UNIPD"))
        self.assertEqual(c.me()["bio"], "ciao")
        with self.assertRaises(ApiError) as e: c.update_profile(email="non-una-mail")
        self.assertEqual(e.exception.status, 400)
        with self.assertRaises(ApiError): c.update_profile(bio="x" * 501)
        c.update_profile(role="server", username="altro", quota_mb=99999)       # disallowed fields ignored
        me = c.me(); self.assertEqual((me["role"], me["username"]), ("user", "prof1"))

    def test_admin_sees_profiles(self):
        self.user("prof2").update_profile(full_name="Anna B")
        self.assertIn("Anna B", [u["full_name"] for u in self.admin().users()])


class TestFiles(Base):
    def test_user_read_insert_not_modify(self):
        u, a = self.user("ugo"), self.admin()
        r = u.upload("photos", "ugo/a.png", self.f("a.png", png_bytes()))
        self.assertEqual(r["path"], "ugo/a.png")
        self.assertEqual([e["name"] for e in u.list("photos", "ugo")], ["a.png"])
        with self.assertRaises(ApiError) as e: u.upload("photos", "ugo/a.png", self.f("a.png", png_bytes()))
        self.assertEqual(e.exception.status, 409)
        for op in (lambda: u.delete("photos", "ugo/a.png"), lambda: u.move("photos", "ugo/a.png", "ugo/b.png")):
            with self.assertRaises(ApiError) as e: op()
            self.assertEqual(e.exception.status, 403)
        self.assertEqual(u.download("photos", "ugo/a.png", self.work / "dl.png").read_bytes(), png_bytes())
        a.move("photos", "ugo/a.png", "ugo/b.png"); a.delete("photos", "ugo/b.png")
        self.assertEqual(a.list("photos", "ugo"), [])

    def test_other_user_can_read_donations(self):
        self.user("dona1").upload("photos", "dona1/x.png", self.f("x.png", png_bytes()))
        self.assertEqual(self.user("dona2").list("photos", "dona1")[0]["name"], "x.png")

    def test_path_traversal(self):
        u = self.user("evil")
        for area in ("photos", "mine"):
            for bad in ("../x.png", "a/../../x.png", "..\\x.png", "a/b:c.png", "con.png"):
                with self.assertRaises(ApiError, msg=bad): u.upload(area, bad, self.f("e.png", png_bytes()))
        with self.assertRaises(ApiError): u.list("photos", "../..")
        with self.assertRaises(ApiError): u.list("mine", "../other")
        with self.assertRaises(ApiError): u.list("sconosciuta")
        with self.assertRaises(ApiError): u.download("photos", "../../server.db", self.work / "z")

    def test_extension_and_magic(self):
        u = self.user("ext")
        with self.assertRaises(ApiError) as e: u.upload("photos", "x.exe", self.f("x.exe", b"MZ" * 10))
        self.assertEqual(e.exception.status, 415)
        with self.assertRaises(ApiError) as e: u.upload("mine", "x.exe", self.f("x.exe", b"MZ" * 10))
        self.assertEqual(e.exception.status, 415)
        with self.assertRaises(ApiError) as e: u.upload("photos", "fake.png", self.f("fake.png", b"non sono un png" * 5))
        self.assertEqual(e.exception.status, 415)

    def test_models_quarantine(self):
        u, a = self.user("mod"), self.admin()
        r = u.upload("models", "Pinna nobilis/best.pt", self.f("best.pt", b"PK-modello" * 100))
        self.assertTrue(r["pending"]); self.assertEqual(r["path"], "_pending/mod/Pinna nobilis/best.pt")
        other = self.user("mod2")
        self.assertNotIn("_pending", [e["name"] for e in other.list("models")])
        with self.assertRaises(ApiError) as e: other.list("models", "_pending")
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(ApiError): other.download("models", "_pending/mod/Pinna nobilis/best.pt", self.work / "q.pt")
        with self.assertRaises(ApiError) as e: u.approve("_pending/mod/Pinna nobilis/best.pt")
        self.assertEqual(e.exception.status, 403)
        # approving without a new name keeps the species folder
        self.assertEqual(a.approve("_pending/mod/Pinna nobilis/best.pt"), "Pinna nobilis/best.pt")
        self.assertEqual(other.download("models", "Pinna nobilis/best.pt", self.work / "m.pt").read_bytes(),
                         b"PK-modello" * 100)
        self.assertIn("Pinna nobilis", [e["name"] for e in other.list("models")])
        # explicit new name
        u.upload("models", "Paracentrotus lividus/m2.pt", self.f("m2.pt", b"PK2" * 50))
        self.assertEqual(a.approve("_pending/mod/Paracentrotus lividus/m2.pt", "Paracentrotus lividus/riccio.pt"),
                         "Paracentrotus lividus/riccio.pt")
        self.assertFalse(a.upload("models", "ufficiale.pt", self.f("uf.pt", b"x" * 50))["pending"])

    def test_models_need_scientific_name_folder(self):
        u = self.user("spec")
        for bad in ("flat.pt", "pesce/x.pt", "pinna nobilis/x.pt", "Pinna/x.pt", "Pinna Nobilis/x.pt"):
            with self.subTest(bad), self.assertRaises(ApiError) as e:
                u.upload("models", bad, self.f("x.pt", b"PK" * 30))
            self.assertEqual(e.exception.status, 422)
        r = u.upload("models", "Pinna nobilis nobilis/y.pt", self.f("y.pt", b"PK" * 30))      # with subspecies
        self.assertTrue(r["pending"])

    def test_server_areas_use_local_folder_names(self):
        """On the lab computer the server data and the local data of the app are the same folder."""
        from common.params import LOCAL_FOLDER_NAMES
        self.admin().upload("datasets", "set1/a.txt", self.f("a.txt", b"x"))
        self.assertTrue((self.data / LOCAL_FOLDER_NAMES["training"] / "set1" / "a.txt").is_file())
        self.user("zed").upload("mine", "n.txt", self.f("n.txt", b"y"))
        self.assertTrue((self.data / LOCAL_FOLDER_NAMES["users"] / "zed" / "n.txt").is_file())

    def test_user_dataset_waits_in_quarantine_and_is_not_merged(self):
        """A dataset uploaded by a user waits in quarantine: the server datasets are not touched, and the user
        can neither list nor read them."""
        a, u = self.admin(), self.user("dsu")
        a.upload("datasets", "coralli/a.png", self.f("a.png", png_bytes()))
        r = u.upload("datasets", "coralli/b.txt", self.f("b.txt", b"label"))
        self.assertTrue(r["pending"])
        self.assertEqual([e["name"] for e in a.list("datasets", "coralli")], ["a.png"])                # untouched
        self.assertEqual([e["name"] for e in a.list("datasets", "_pending/dsu/coralli")], ["b.txt"])  # waiting
        with self.assertRaises(ApiError) as e: u.upload("datasets", "coralli/b.txt", self.f("b.txt", b"other"))
        self.assertEqual(e.exception.status, 409)                                                       # never overwritten
        self.assertIn("coralli", [e["name"] for e in u.list("datasets", "")])          # the approved ones are readable...
        with self.assertRaises(ApiError) as e: u.list("datasets", "_pending/dsu/coralli")
        self.assertEqual(e.exception.status, 403)                                       # ...the ones waiting are not

    def test_mkdir_rules(self):
        u, a = self.user("dir"), self.admin()
        with self.assertRaises(ApiError) as e: u.mkdir("datasets", "nuovo")
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(ApiError) as e: u.mkdir("models", "cartella")
        self.assertEqual(e.exception.status, 403)
        a.mkdir("models", "famiglie")
        self.assertEqual(a.mkdir("datasets", "nuovo"), "nuovo")

    def test_download_resume_and_cancel(self):
        a = self.admin(); data = os.urandom(3_000_000)
        a.upload("datasets", "big.zip", self.f("big.zip", data))
        dest = self.work / "big_dl.zip"; n = [0]
        def cancel():
            n[0] += 1; return n[0] > 1
        with self.assertRaises(Cancelled): a.download("datasets", "big.zip", dest, None, cancel)
        part = Path(str(dest) + ".part")
        self.assertTrue(part.exists() and 0 < part.stat().st_size < len(data))
        a.download("datasets", "big.zip", dest)
        self.assertEqual(dest.read_bytes(), data); self.assertFalse(part.exists())

    def test_admin_delete_dir_and_root_protected(self):
        a = self.admin(); a.upload("datasets", "zz/d.txt", self.f("d.txt", b"ciao")); a.delete("datasets", "zz")
        with self.assertRaises(ApiError): a.delete("datasets", "")
        with self.assertRaises(ApiError): a.delete("models", "_pending")

    def test_events_log(self):
        a = self.admin(); self.user("event1").upload("photos", "event1/e.png", self.f("e.png", png_bytes()))
        self.assertTrue(any(e["action"] == "upload" and e["username"] == "event1" for e in a.events()))
        with self.assertRaises(ApiError): self.user("event1").events()


class TestMine(Base):
    def test_owner_has_full_control(self):
        u = self.user("own1")
        u.upload("mine", "doc/a.png", self.f("a.png", png_bytes()))
        u.upload("mine", "doc/a.png", self.f("a.png", png_bytes()))              # overwriting is allowed
        u.mkdir("mine", "altra"); u.move("mine", "doc/a.png", "altra/b.png")
        self.assertEqual([e["name"] for e in u.list("mine", "altra")], ["b.png"])
        self.assertEqual(u.download("mine", "altra/b.png", self.work / "m.png").read_bytes(), png_bytes())
        u.delete("mine", "altra")
        self.assertNotIn("altra", [e["name"] for e in u.list("mine")])
        u.upload("mine", "m.pt", self.f("m.pt", b"modello"))                     # private models: no quarantine
        self.assertIn("m.pt", [e["name"] for e in u.list("mine")])

    def test_private_to_each_user(self):
        a, b = self.user("own2"), self.user("own3")
        a.upload("mine", "segreto.txt", self.f("s.txt", b"dati"))
        self.assertEqual(b.list("mine"), [])
        with self.assertRaises(ApiError) as e: b.download("mine", "segreto.txt", self.work / "x.txt")
        self.assertEqual(e.exception.status, 404)

    def test_quota_and_usage(self):
        a = self.admin(); u = self.user("own4")
        uid = u.me()["id"]
        a.update_user(uid, quota_mb=1)
        self.assertEqual(u.usage()["quota"], 1 << 20)
        u.upload("mine", "a.csv", self.f("a.csv", b"x" * 700_000))
        self.assertEqual(u.usage()["used"], 700_000)
        with self.assertRaises(ApiError) as e: u.upload("mine", "b.csv", self.f("b.csv", b"x" * 700_000))
        self.assertEqual(e.exception.status, 413)
        u.upload("mine", "a.csv", self.f("a.csv", b"y" * 900_000))               # overwrite: the difference counts
        with self.assertRaises(ApiError): u.update_user(uid, quota_mb=5)         # the user cannot change their own quota


class TestSession(Base):
    def test_online_then_offline_and_resume(self):
        store = LocalStore(Path(self.tmp.name) / "local1"); s = Session(store)
        s.register("sess", "password123", self.url)
        self.assertEqual(s.login("sess", "password123", self.url), "online")
        self.assertTrue(s.can("files.insert") and s.can("mine.manage")); self.assertFalse(s.can("users.manage"))
        s2 = Session(store)
        self.assertTrue(s2.resume() and s2.online); self.assertEqual(s2.username, "sess")
        s2.logout(); self.assertFalse(Session(store).resume())
        dead = "http://127.0.0.1:9"
        store.remember_user({"username": "sess", "role": "user"}, "password123", dead)
        s3 = Session(store)
        self.assertEqual(s3.login("sess", "password123", dead), "offline")
        self.assertFalse(s3.online or s3.can("files.insert")); self.assertTrue(s3.can("analysis.run"))
        with self.assertRaises(OfflineError): Session(store).login("sess", "sbagliata", dead)
        with self.assertRaises(OfflineError): Session(store).login("sconosciuto", "password123", dead)

    def test_admin_signs_in_offline_and_works_locally(self):
        store = LocalStore(Path(self.tmp.name) / "local_adm"); s = Session(store)
        store.remember_user({"username": "boss", "role": "server"}, "password123", self.url)   # earlier online sign-in
        s2 = Session(store)
        self.assertEqual(s2.login("boss", "password123", "http://127.0.0.1:9"), "offline")      # server down / other address
        self.assertTrue(s2.is_admin and not s2.online)
        self.assertTrue(s2.can("analysis.run") and s2.can("training.run"))
        self.assertFalse(s2.can("users.manage") or s2.can("files.insert"))                      # server actions are off

    def test_wrong_password_online_is_not_offline_fallback(self):
        store = LocalStore(Path(self.tmp.name) / "local2")
        s = Session(store); s.register("sess2", "password123", self.url); s.login("sess2", "password123", self.url)
        with self.assertRaises(ApiError) as e: Session(store).login("sess2", "errata123", self.url)
        self.assertEqual(e.exception.status, 401)

    def test_admin_permissions(self):
        s = Session(LocalStore(Path(self.tmp.name) / "local3")); s.login("admin", "adminpass1", self.url)
        for p in ("users.manage", "files.modify", "files.delete", "training.manage", "models.approve"):
            self.assertTrue(s.can(p), p)

    def test_key_login_persists_and_guest(self):
        store = LocalStore(Path(self.tmp.name) / "local5")
        s = Session(store); s.register("sk1234", "password123", self.url)
        s.login("sk1234", "password123", self.url, key=KEY)
        self.assertTrue(s.is_admin and s.can("users.manage"))
        self.assertEqual(store._users()["sk1234"]["role"], "server")             # locally: permanent administrator
        s2 = Session(LocalStore(Path(self.tmp.name) / "local5b")); s2.login("sk1234", "password123", self.url)
        self.assertTrue(s2.is_admin)                                              # even without a key
        with self.assertRaises(ApiError) as e:
            Session(LocalStore(Path(self.tmp.name) / "local6")).register("sk9999", "password123", self.url, key="no")
        self.assertEqual(e.exception.status, 403)
        g = Session(LocalStore(Path(self.tmp.name) / "local7")); g.start_offline()
        self.assertTrue(g.logged_in and g.is_guest and not g.online and not g.is_admin)
        self.assertTrue(g.can("analysis.run") and g.can("training.run")); self.assertFalse(g.can("files.read") or g.can("mine.manage"))

    def test_profile_saved_locally_for_offline(self):
        store = LocalStore(Path(self.tmp.name) / "local8"); s = Session(store)
        s.register("pf1234", "password123", self.url); s.login("pf1234", "password123", self.url)
        s.save_profile(full_name="Luca V", organization="Nautilus")
        self.assertEqual(store.profile("pf1234")["full_name"], "Luca V")
        dead = "http://127.0.0.1:9"
        store.remember_user(s.user, "password123", dead)
        s2 = Session(store); s2.login("pf1234", "password123", dead)
        self.assertFalse(s2.online); self.assertEqual(s2.profile()["organization"], "Nautilus")
        with self.assertRaises(OfflineError): s2.save_profile(full_name="X")

    def test_local_folders_per_user(self):
        store = LocalStore(Path(self.tmp.name) / "local9")
        self.assertTrue(store.folders("a")["photos"].endswith("photos"))
        store.set_folders("a", {"photos": "/x/p", "nonvalida": "/y"})
        self.assertEqual(store.folders("a")["photos"], "/x/p"); self.assertNotIn("nonvalida", store.folders("a"))
        self.assertNotEqual(store.folders("b")["photos"], "/x/p")
        app = LocalStore(Path(self.tmp.name) / "local10", {"models": "/proj/models"})
        self.assertEqual(app.folders("a")["models"], "/proj/models"); self.assertTrue(app.folders("a")["photos"].endswith("photos"))

    def test_local_files_do_not_hold_password(self):
        store = LocalStore(Path(self.tmp.name) / "local4")
        Session(store).register("pwl", "password123", self.url); Session(store).login("pwl", "password123", self.url)
        for p in store.dir.iterdir():
            if p.is_file(): self.assertNotIn("password123", p.read_text())

class TestSpeciesReview(Base):

    def test_submit_and_approve(self):
        u, other, a = self.user("bio"), self.user("bio2"), self.admin()
        for name in ("a", "b"):
            u.upload("species", f"Pinna nobilis/{name}.png", self.f(f"{name}.png", png_bytes()))
        sub = u.submit_species("Pinna nobilis")
        self.assertEqual((sub["species"], sub["photos"]), ("Pinna nobilis", 2))
        self.assertEqual([s["id"] for s in u.species_submissions()], [sub["id"]])        # l'utente vede le sue
        self.assertEqual(other.species_submissions(), [])                                # non quelle degli altri
        self.assertIn(sub["id"], [s["id"] for s in a.species_submissions("pending")])    # l'admin le vede tutte
        with self.assertRaises(ApiError) as e:
            u.approve_submission(sub["id"])
        self.assertEqual(e.exception.status, 403)                                        # approva solo l'admin
        res = a.approve_submission(sub["id"])
        self.assertEqual(res["photos"], 2)
        self.assertEqual(u.species_submissions()[0]["status"], "approved")
        self.assertIn(res["folder"], [x["name"] for x in other.list("species", "Pinna nobilis")])   # il dataset è di tutti
        with self.assertRaises(ApiError) as e:
            a.approve_submission(sub["id"])
        self.assertEqual(e.exception.status, 409)                                        # non si approva due volte

    def test_reject_keeps_the_record_but_not_the_photos(self):
        u, a = self.user("bio3"), self.admin()
        u.upload("species", "Epinephelus marginatus/a.png", self.f("r.png", png_bytes()))
        sub = u.submit_species("Epinephelus marginatus")
        a.reject_submission(sub["id"])
        self.assertEqual(u.species_submissions()[0]["status"], "rejected")
        self.assertNotIn("Epinephelus marginatus", [x["name"] for x in u.list("species")])


class TestDatasetAndModelReview(Base):

    def upload_dataset(self, u, name, labels=True):
        u.upload("datasets", f"{name}/data.yaml", self.f("data.yaml", b"names: [x]"))
        u.upload("datasets", f"{name}/images/a.png", self.f("a.png", png_bytes()))
        if labels:
            u.upload("datasets", f"{name}/labels/a.txt", self.f("a.txt", b"0 0.5 0.5 0.2 0.2"))

    def upload_model(self, u, species, name):
        u.upload("models", f"{species}/{name}.pt", self.f(f"{name}.pt", b"PK" * 30))
        u.upload("models", f"{species}/{name}.json", self.f(f"{name}.json", b"{}"))

    def test_dataset_submit_review_and_approve(self):
        u, a = self.user("dsr"), self.admin()
        self.upload_dataset(u, "coralli_r")
        sub = u.submit_dataset("coralli_r")
        self.assertEqual((sub["kind"], sub["images"]), ("dataset", 1))
        self.assertIn(sub["id"], [s["id"] for s in a.species_submissions("pending", kind="dataset")])
        self.assertNotIn(sub["id"], [s["id"] for s in a.species_submissions("pending", kind="model")])
        with self.assertRaises(ApiError) as e:
            u.approve_submission(sub["id"])
        self.assertEqual(e.exception.status, 403)                                   # approva solo l'admin
        a.approve_submission(sub["id"])
        self.assertIn("coralli_r", [x["name"] for x in a.list("datasets")])
        self.assertTrue(any(x["name"].startswith("coralli_r_dsr_") for x in a.list("datasets", "coralli_r")))
        row = [s for s in a.species_submissions(kind="dataset") if s["id"] == sub["id"]][0]
        self.assertEqual(row["status"], "approved")
        self.assertTrue(row["reviewed_by"])

    def test_users_can_read_an_approved_dataset_but_not_a_pending_one(self):
        a, owner, other = self.admin(), self.user("dsv1"), self.user("dsv2")
        self.upload_dataset(owner, "coralli_v")
        done = a.approve_submission(owner.submit_dataset("coralli_v")["id"])
        self.assertIn(done["name"].split("/")[0], [e["name"] for e in other.list("datasets", "")])
        self.assertIn("data.yaml", [e["name"] for e in other.list("datasets", done["name"])])
        self.upload_dataset(owner, "coralli_w")
        owner.submit_dataset("coralli_w")                                                 # waits for review
        with self.assertRaises(ApiError) as e:
            other.list("datasets", "_pending/dsv1/coralli_w")
        self.assertEqual(e.exception.status, 403)

    def test_a_dataset_without_labels_is_refused(self):
        u = self.user("dsr2")
        self.upload_dataset(u, "senza_label", labels=False)
        with self.assertRaises(ApiError) as e:
            u.submit_dataset("senza_label")
        self.assertEqual(e.exception.status, 422)

    def test_model_submit_and_approve_moves_the_metadata_too(self):
        u, a = self.user("mdr"), self.admin()
        self.upload_model(u, "Pinna nobilis", "mdr")
        sub = u.submit_model("Pinna nobilis", "mdr.pt")
        self.assertEqual(sub["kind"], "model")
        a.approve_submission(sub["id"])
        names = [x["name"] for x in a.list("models", "Pinna nobilis")]
        self.assertIn("mdr.pt", names)
        self.assertIn("mdr.json", names)

    def test_the_catalog_shows_approved_items_to_everyone_with_the_date_only(self):
        u, other, a = self.user("cat1"), self.user("cat2"), self.admin()
        self.upload_model(u, "Sparus aurata", "cat")
        sub = u.submit_model("Sparus aurata", "cat.pt")
        self.assertEqual([i for i in other.catalog("model") if i["uploader"] == "cat1"], [])   # not approved yet
        a.approve_submission(sub["id"])
        (item,) = [i for i in other.catalog("model") if i["uploader"] == "cat1"]
        self.assertEqual((item["species"], item["path"]), ("Sparus aurata", "Sparus aurata/cat.pt"))
        self.assertTrue(item["approved_by"])
        self.assertRegex(item["date"], r"^\d{4}-\d{2}-\d{2}$")                      # the date, never the time
        self.assertNotIn("created", item)

    def test_the_catalog_is_in_alphabetical_order_of_species(self):
        u, a = self.user("cat3"), self.admin()
        for species, name in (("Zeus faber", "z"), ("Apogon imberbis", "ap")):
            self.upload_model(u, species, name)
            a.approve_submission(u.submit_model(species, f"{name}.pt")["id"])
        species = [i["species"] for i in u.catalog("model")]
        self.assertEqual(species, sorted(species, key=str.lower))

    def test_the_dataset_catalog_is_open_to_every_account(self):
        u, a = self.user("cat4"), self.admin()
        self.assertIsInstance(u.catalog("dataset"), list)
        self.assertIsInstance(a.catalog("dataset"), list)

    def test_an_unknown_kind_of_catalog_is_not_found(self):
        u = self.user("cat5")
        with self.assertRaises(ApiError) as e:
            u.catalog("whatever")
        self.assertEqual(e.exception.status, 404)

    def test_what_an_admin_publishes_needs_no_approval_but_is_in_the_catalog(self):
        a, other = self.admin(), self.user("cat6")
        self.upload_model(a, "Sparus aurata", "adm")
        res = a.submit_model("Sparus aurata", "adm.pt")
        self.assertFalse(res["pending"])
        self.assertIn("Sparus aurata/adm.pt", [i["path"] for i in other.catalog("model")])

    def test_the_dataset_catalog_is_open_to_users_and_lists_the_species(self):
        a, owner, other = self.admin(), self.user("dsc1"), self.user("dsc2")
        owner.upload("datasets", "multi/data.yaml",
                     self.f("data.yaml", b"names:\n  0: Pinna nobilis\n  1: Sparus aurata\n"))
        owner.upload("datasets", "multi/images/a.png", self.f("a.png", png_bytes()))
        owner.upload("datasets", "multi/labels/a.txt", self.f("a.txt", b"0 0.5 0.5 0.2 0.2"))
        a.approve_submission(owner.submit_dataset("multi")["id"])
        item = [i for i in other.catalog("dataset") if i["path"].startswith("multi/multi_dsc1_")][0]
        self.assertEqual(item["classes"], ["Pinna nobilis", "Sparus aurata"])
        self.assertEqual(item["uploader"], "dsc1")

    def put_dataset(self, u, name, yaml):
        u.upload("datasets", f"{name}/data.yaml", self.f("data.yaml", yaml))
        u.upload("datasets", f"{name}/images/a.png", self.f("a.png", png_bytes()))
        u.upload("datasets", f"{name}/labels/a.txt", self.f("a.txt", b"0 0.5 0.5 0.2 0.2"))

    def test_an_approved_dataset_is_named_after_its_species_user_and_date(self):
        a, u = self.admin(), self.user("dsn1")
        self.put_dataset(u, "minirename", b"names:\n  0: Pinna nobilis\n")
        done = a.approve_submission(u.submit_dataset("minirename")["id"])
        self.assertRegex(done["name"], r"^Pinna nobilis/Pinna nobilis_dsn1_\d{4}-\d{2}-\d{2}$")
        self.assertIn("Pinna nobilis", [e["name"] for e in a.list("datasets", "")])             # a folder for the species...
        self.assertIn(done["name"].split("/")[1], [e["name"] for e in a.list("datasets", "Pinna nobilis")])   # ...with the dataset inside
        self.assertNotIn("minirename", [e["name"] for e in a.list("datasets", "")])

    def test_two_datasets_of_the_same_day_do_not_clash(self):
        a, u = self.admin(), self.user("dsn2")
        names = []
        for n in ("dup1", "dup2"):
            self.put_dataset(u, n, b"names:\n  0: Sparus aurata\n")
            names.append(a.approve_submission(u.submit_dataset(n)["id"])["name"])
        self.assertEqual(names[1], names[0] + "_2")

    def test_a_dataset_with_several_species_keeps_its_own_name(self):
        a, u = self.admin(), self.user("dsn3")
        self.put_dataset(u, "multid", b"names:\n  0: Pinna nobilis\n  1: Sparus aurata\n")
        done = a.approve_submission(u.submit_dataset("multid")["id"])
        self.assertRegex(done["name"], r"^multid/multid_dsn3_\d{4}-\d{2}-\d{2}$")

if __name__ == "__main__":
    unittest.main(verbosity=1)
