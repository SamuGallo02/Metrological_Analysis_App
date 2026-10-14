"""Code repair and update, against a fake GitHub running on localhost (no real network)."""
import hashlib, io, json, os, re, shutil, sys, tempfile, threading, unittest, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.ambient.updater import apply, config, manifest, prefs, startup, versions

REPO = "me/app"


def sha_of(name: str) -> str:
    return hashlib.sha1(name.encode()).hexdigest()


class FakeGitHub:
    """Serves releases, commits, archives and raw files for a few fake commits."""

    def __init__(self):
        self.commits = {}            # sha -> {path: bytes}
        self.head = ""
        self.release = None          # (tag, sha) or None
        self.hits = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/octet-stream"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = unquote(self.path)
                fake.hits.append(path)
                if path == f"/api/repos/{REPO}/releases/latest":
                    if not fake.release:
                        return self._send(404, b"{}")
                    return self._send(200, json.dumps({"tag_name": fake.release[0], "published_at": "2026-01-01"}).encode())
                m = re.fullmatch(rf"/api/repos/{REPO}/commits/(.+)", path)
                if m:
                    ref = m.group(1)
                    sha = fake.release[1] if fake.release and ref == fake.release[0] else fake.head if ref == "main" else ref
                    return self._send(200, json.dumps({"sha": sha}).encode())
                m = re.fullmatch(rf"/web/{REPO}/archive/(.+)\.zip", path)
                if m:
                    ref = m.group(1)
                    sha = fake.head if ref == "main" else ref
                    if sha not in fake.commits:
                        return self._send(404, b"")
                    return self._send(200, fake.zip(sha))
                m = re.fullmatch(rf"/raw/{REPO}/([0-9a-f]{{40}})/(.+)", path)
                if m and m.group(1) in fake.commits and m.group(2) in fake.commits[m.group(1)]:
                    return self._send(200, fake.commits[m.group(1)][m.group(2)])
                self._send(404, b"")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{self.httpd.server_port}"
        os.environ.update(AM_GH_API=base + "/api", AM_GH_WEB=base + "/web", AM_GH_RAW=base + "/raw", AM_GH_REPO=REPO)

    def zip(self, sha):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.comment = sha.encode()
            for p, data in self.commits[sha].items():
                info = zipfile.ZipInfo(f"app-main/{p}")
                if p.endswith((".sh", ".command")):
                    info.external_attr = 0o755 << 16
                z.writestr(info, data)
        return buf.getvalue()

    def add(self, name, files, head=True):
        sha = sha_of(name)
        self.commits[sha] = files
        if head:
            self.head = sha
        return sha

    def close(self):
        self.httpd.shutdown()


V1 = {"main.py": b"print('v1')\n", "common/a.py": b"A1\n", "common/b.py": b"B1\n" * 50,
      "common/ambient/requirements/core.txt": b"numpy\n",
      "common/launchers/AnalisiMetrologica.vbs": b"vbs\n",
      "common/launchers/AvviaAnalisiMetrologica.sh": b"#!/bin/sh\n",
      "common/launchers/AvviaAnalisiMetrologica.command": b"#!/bin/sh\n",
      "tests/t.py": b"t\n", "server/s.py": b"s\n", "docs/d.md": b"d\n", "deploy/x": b"x\n", ".github/w.yml": b"w\n"}


class UpdaterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gh = FakeGitHub()

    @classmethod
    def tearDownClass(cls):
        cls.gh.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gh.release = None
        self.gh.commits.clear()
        self.sha1 = self.gh.add("v1", dict(V1))
        self.install("windows")

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, os_name):
        """What the installer does: a first update on an empty folder."""
        v = versions.latest()
        apply.update(self.root, v, os_name)

    # -- filters ------------------------------------------------------------------
    def test_only_wanted_files_installed(self):
        names = set(manifest.load(self.root)["files"])
        self.assertIn("main.py", names)
        self.assertIn("common/launchers/AnalisiMetrologica.vbs", names)
        self.assertNotIn("common/launchers/AvviaAnalisiMetrologica.sh", names)
        self.assertNotIn("common/launchers/AvviaAnalisiMetrologica.command", names)
        for skipped in ("tests/t.py", "server/s.py", "docs/d.md", "deploy/x", ".github/w.yml"):
            self.assertNotIn(skipped, names)
            self.assertFalse((self.root / skipped).exists())
        self.assertEqual(manifest.load(self.root)["sha"], self.sha1)

    def test_launcher_follows_os(self):
        self.assertTrue(config.wanted("common/launchers/AvviaAnalisiMetrologica.sh", "linux"))
        self.assertFalse(config.wanted("common/launchers/AnalisiMetrologica.vbs", "linux"))
        self.assertTrue(config.wanted("common/a.py", "macos"))

    def test_installer_lists_match(self):
        src = (Path(__file__).resolve().parent.parent / "common/ambient/distribution/installer_gui.py").read_text(encoding="utf-8")
        ns = {}
        for name in ("SERVER_ONLY_DIRS", "LAUNCHER_DIR", "LAUNCHERS", "VERSION_FILE"):
            m = re.search(rf"^{name} = (.+?)(?=\n[A-Za-z_]+ =|\n\n)", src, re.S | re.M)
            ns[name] = eval(m.group(1))
        self.assertEqual(ns["SERVER_ONLY_DIRS"], config.SKIP_DIRS)
        self.assertEqual(ns["LAUNCHER_DIR"], config.LAUNCHER_DIR)
        self.assertEqual(ns["LAUNCHERS"], config.LAUNCHERS)
        self.assertEqual(ns["VERSION_FILE"], config.VERSION_FILE)

    def test_installer_writes_a_manifest_the_updater_accepts(self):
        from common.ambient.distribution import installer_gui as ig
        dest = Path(tempfile.mkdtemp(dir=self.tmp.name)) / "fresh"
        base = os.environ["AM_GH_WEB"]
        old = ig.SOURCE_URL
        ig.SOURCE_URL = f"{base}/{REPO}/archive/main.zip"
        try:
            ig.Pipeline(dest, "linux", False, False, lambda *a: None, lambda *a: None).download_code()
        finally:
            ig.SOURCE_URL = old
        rec = manifest.load(dest)
        self.assertEqual(rec["sha"], self.sha1)
        self.assertIn("common/launchers/AvviaAnalisiMetrologica.sh", rec["files"])
        self.assertNotIn("common/launchers/AnalisiMetrologica.vbs", rec["files"])
        self.assertFalse((dest / "tests").exists())
        self.assertEqual(manifest.verify(dest, True), [])
        res = apply.update(dest, versions.latest(), "linux")
        self.assertEqual((res["updated"], res["added"], res["removed"]), ([], [], []))   # already up to date

    # -- verify / repair ----------------------------------------------------------
    def test_healthy_install_has_no_problems(self):
        self.assertEqual(manifest.verify(self.root, deep=True), [])

    def test_detects_missing_truncated_and_corrupted(self):
        (self.root / "common/a.py").unlink()
        (self.root / "common/b.py").write_bytes(b"B1\n")                       # truncated: size differs
        (self.root / "main.py").write_bytes(b"print('v2')\n")                   # same size, other content
        quick = {p.rel: p.kind for p in manifest.verify(self.root)}
        self.assertEqual(quick, {"common/a.py": "missing", "common/b.py": "size"})
        deep = {p.rel: p.kind for p in manifest.verify(self.root, deep=True)}
        self.assertEqual(deep["main.py"], "hash")
        self.assertEqual(len(deep), 3)

    def test_repair_downloads_only_damaged_files(self):
        (self.root / "common/a.py").unlink()
        (self.root / "main.py").write_bytes(b"print('v2')\n")
        self.gh.hits.clear()
        rec = manifest.load(self.root)
        fixed, failed = apply.repair(self.root, manifest.verify(self.root, True), rec)
        self.assertEqual((sorted(fixed), failed), (["common/a.py", "main.py"], []))
        self.assertEqual(manifest.verify(self.root, True), [])
        raws = [h for h in self.gh.hits if h.startswith("/raw/")]
        self.assertEqual(sorted(h.rsplit("/", 1)[-1] for h in raws), ["a.py", "main.py"])
        self.assertFalse([h for h in self.gh.hits if "/archive/" in h])

    def test_repair_falls_back_to_archive(self):
        (self.root / "common/a.py").unlink()
        saved = self.gh.commits[self.sha1]["common/a.py"]
        orig = source_fetch = apply.source.fetch_file
        apply.source.fetch_file = lambda *a, **k: (_ for _ in ()).throw(apply.source.SourceError("raw down"))
        try:
            fixed, failed = apply.repair(self.root, manifest.verify(self.root), manifest.load(self.root))
        finally:
            apply.source.fetch_file = orig
        self.assertEqual((fixed, failed), (["common/a.py"], []))
        self.assertEqual((self.root / "common/a.py").read_bytes(), saved)

    def test_repair_reports_unrecoverable(self):
        (self.root / "common/a.py").unlink()
        self.gh.commits.clear()                                                  # GitHub forgot the commit
        fixed, failed = apply.repair(self.root, manifest.verify(self.root), manifest.load(self.root))
        self.assertEqual((fixed, failed), ([], ["common/a.py"]))

    def test_startup_repairs_silently(self):
        (self.root / "common/b.py").unlink()
        self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "repaired")
        self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "ok")

    def test_startup_skips_git_and_unrecorded(self):
        (self.root / ".git").mkdir()
        (self.root / "common/a.py").unlink()
        self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "skipped")
        self.assertFalse((self.root / "common/a.py").exists())
        shutil.rmtree(self.root / ".git")
        (self.root / config.VERSION_FILE).unlink()
        self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "skipped")

    def test_startup_failure_when_offline(self):
        (self.root / "common/a.py").unlink()
        self.gh.commits.clear()
        self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "failed")

    # -- update -------------------------------------------------------------------
    def v2(self, **extra):
        files = dict(V1)
        files["common/a.py"] = b"A2\n"                 # changed
        files["common/new.py"] = b"new\n"              # added
        del files["common/b.py"]                       # removed
        files.update(extra)
        return self.gh.add("v2", files)

    def test_update_changes_only_what_differs(self):
        sha2 = self.v2()
        mtime = (self.root / "main.py").stat().st_mtime_ns
        res = apply.update(self.root, versions.latest(), "windows")
        self.assertEqual(res["updated"], ["common/a.py"])
        self.assertEqual(res["added"], ["common/new.py"])
        self.assertEqual(res["removed"], ["common/b.py"])
        self.assertFalse(res["requirements_changed"])
        self.assertEqual((self.root / "main.py").stat().st_mtime_ns, mtime)      # untouched file not rewritten
        self.assertFalse((self.root / "common/b.py").exists())
        self.assertEqual(manifest.load(self.root)["sha"], sha2)
        self.assertEqual(manifest.verify(self.root, True), [])

    def test_update_flags_requirements_and_keeps_user_data(self):
        (self.root / "librery").mkdir(exist_ok=True)
        (self.root / "librery/venv").mkdir()
        (self.root / "librery/venv/x").write_text("keep")
        (self.root / "mine.txt").write_text("keep")
        self.v2(**{"common/ambient/requirements/core.txt": b"numpy\nopencv\n"})
        res = apply.update(self.root, versions.latest(), "windows")
        self.assertTrue(res["requirements_changed"])
        self.assertEqual((self.root / "librery/venv/x").read_text(), "keep")
        self.assertEqual((self.root / "mine.txt").read_text(), "keep")

    def test_update_repairs_while_updating(self):
        self.v2()
        (self.root / "common/a.py").unlink()
        apply.update(self.root, versions.latest(), "windows")
        self.assertEqual((self.root / "common/a.py").read_bytes(), b"A2\n")

    def test_latest_prefers_release_over_branch(self):
        sha_rel = self.gh.add("rel", dict(V1, **{"main.py": b"rel\n"}), head=False)
        self.v2()
        self.gh.release = ("v1.1", sha_rel)
        v = versions.latest()
        self.assertEqual((v.label, v.sha), ("v1.1", sha_rel))
        self.gh.release = None
        self.assertEqual(versions.latest().sha, sha_of("v2"))

    def test_auto_mode_updates_and_ask_mode_does_not(self):
        self.v2()
        prefs.save(self.root, mode="ask")
        self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "ok")
        prefs.save(self.root, mode="auto", last_check=0)
        self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "updated")
        self.assertEqual(manifest.load(self.root)["sha"], sha_of("v2"))
        self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "ok")      # throttled: no 2nd check

    def test_auto_mode_ignores_network_errors(self):
        prefs.save(self.root, mode="auto", last_check=0)
        self.gh.commits.clear()
        self.gh.head = "0" * 40
        saved, os.environ["AM_GH_API"] = os.environ["AM_GH_API"], "http://127.0.0.1:9/none"
        try:
            self.assertEqual(startup.run(self.root, "windows", log=lambda *_: None), "ok")
        finally:
            os.environ["AM_GH_API"] = saved

    def test_path_traversal_in_archive_is_refused(self):
        self.gh.add("evil", dict(V1, **{"../evil.py": b"x"}))
        try:
            apply.update(self.root, versions.latest(), "windows")
        except Exception:
            pass
        self.assertFalse((self.root.parent / "evil.py").exists())


if __name__ == "__main__":
    unittest.main()
