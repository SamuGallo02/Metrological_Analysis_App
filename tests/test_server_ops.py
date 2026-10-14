"""Operational tools of the server: rate limit, statistics, backup/restore, command line."""
import json
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.errors import AppError
from server import __main__ as cli
from server.ops import backup as bk
from server.ops import network, stats
from server.ratelimit import RateLimiter
from tests.util import TestServer


def get(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def login(url, user="admin", pw="adminpass1"):
    req = urllib.request.Request(url + "/api/login", json.dumps({"username": user, "password": pw}).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())["token"]


class TestRateLimit(unittest.TestCase):
    def test_limiter_blocks_then_recovers(self):
        rl = RateLimiter(3, window=0.2)
        for _ in range(3):
            rl.hit("a")
        with self.assertRaises(AppError) as cm:
            rl.hit("a")
        self.assertEqual(cm.exception.status, 429)
        rl.hit("b")                                     # another address is not affected
        import time
        time.sleep(0.25)
        rl.hit("a")

    def test_zero_means_unlimited(self):
        rl = RateLimiter(0)
        for _ in range(1000):
            rl.hit("a")

    def test_server_answers_429(self):
        srv = TestServer(rate_limit=5)
        try:
            codes = [get(srv.url + "/api/me")[0] for _ in range(8)]
            self.assertIn(429, codes)
            self.assertEqual(get(srv.url + "/api/health")[0], 200)      # health check is never limited
        finally:
            srv.close()


class TestHealthAndStats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = TestServer(rate_limit=0)

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def test_health_has_uptime(self):
        code, body = get(self.srv.url + "/api/health")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertIn("uptime", body)

    def test_stats_admin_only(self):
        self.assertEqual(get(self.srv.url + "/api/stats")[0], 401)
        code, body = get(self.srv.url + "/api/stats", login(self.srv.url))
        self.assertEqual(code, 200)
        self.assertEqual(body["users"], 1)
        self.assertEqual(body["admins"], 1)
        self.assertGreater(body["disk_free"], 0)
        self.assertGreaterEqual(body["requests"], 1)


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        cli._db(self.data).create_user("anna", "password123")
        (self.data / "models").mkdir()
        (self.data / "models" / "x.txt").write_text("hello")

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_and_restore(self):
        out = bk.backup_db(self.data / "server.db", self.data / "backups")
        cli._db(self.data).create_user("bruno", "password123")
        self.assertEqual(len(cli._db(self.data).list_users()), 2)
        saved = bk.restore_db(out, self.data / "server.db")
        self.assertTrue(saved.exists())
        self.assertEqual([u["username"] for u in cli._db(self.data).list_users()], ["anna"])

    def test_restore_rejects_garbage_and_running_server(self):
        bad = self.data / "bad.db"
        bad.write_bytes(b"not a database" * 100)
        with self.assertRaises(bk.BackupError):
            bk.restore_db(bad, self.data / "server.db")
        good = bk.backup_db(self.data / "server.db", self.data / "backups")
        with self.assertRaises(bk.BackupError):
            bk.restore_db(good, self.data / "server.db", server_running=True)

    def test_files_archive_excludes_backups_and_prune_keeps_newest(self):
        dest = self.data / "backups"
        archive = bk.backup_files(self.data, dest)
        import tarfile
        names = tarfile.open(archive).getnames()
        self.assertTrue(any(n.endswith("x.txt") for n in names))
        self.assertFalse(any(n.startswith("backups") for n in names))
        for i in range(4):
            (dest / f"server-2026010{i}-000000.db").write_bytes(b"x")
        bk.prune(dest, 2)
        self.assertEqual(len(bk.list_backups(dest)), 2)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = ["--data", self.tmp.name]

    def tearDown(self):
        self.tmp.cleanup()

    def test_users_commands(self):
        self.assertEqual(cli.main(self.d + ["create-admin", "root", "--password", "password123"]), 0)
        db = cli._db(Path(self.tmp.name))
        db.create_user("mario", "password123")
        self.assertEqual(cli.main(self.d + ["users", "disable", "mario"]), 0)
        self.assertFalse(cli._find_user(db, "mario")["active"])
        self.assertEqual(cli.main(self.d + ["users", "enable", "mario"]), 0)
        self.assertTrue(cli._find_user(db, "mario")["active"])
        self.assertEqual(cli.main(self.d + ["users", "passwd", "mario", "--password", "newpassword1"]), 0)
        db.authenticate("mario", "newpassword1")
        self.assertEqual(cli.main(self.d + ["users", "disable", "nobody"]), 1)

    def test_status_backup_doctor(self):
        cli.main(self.d + ["create-admin", "root", "--password", "password123"])
        self.assertEqual(cli.main(self.d + ["status"]), 0)
        self.assertEqual(cli.main(self.d + ["backup", "--keep", "2"]), 0)
        self.assertEqual(cli.main(self.d + ["doctor"]), 0)

    def test_public_flag_parses_and_implies_exposure(self):
        a = cli._build_parser().parse_args(["serve", "--public"])
        self.assertTrue(a.public)
        self.assertEqual(a.host, "127.0.0.1")           # the tunnel reaches the local port only

    def test_weak_key_detection(self):
        self.assertTrue(cli.weak_key("abcd"))
        self.assertFalse(cli.weak_key("a" * 16))
        self.assertFalse(cli.weak_key("sha256:" + "0" * 64))
        self.assertFalse(cli.weak_key(""))


class TestNetwork(unittest.TestCase):
    def test_loopback_and_addresses(self):
        self.assertTrue(network.is_loopback("127.0.0.1"))
        self.assertFalse(network.is_loopback("0.0.0.0"))
        for a in network.lan_addresses():
            self.assertFalse(a.startswith("127."))


if __name__ == "__main__":
    unittest.main()
