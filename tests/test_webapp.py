"""Web application: pages, translations and the analysis queue (with a fake engine: standard library only)."""
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from common.errors import AppError
from common.params import ROLE_SERVER
from server.app import make_server
from server.db import Database
from webapp.engine import AnalysisEngine
from webapp.handler import WebHandler, load_strings
from webapp.jobs import JobManager, report_csv

from tests.util import png_bytes

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


class FakeEngine:
    """Two pairs, one subject each; `gate` (if set) holds the job until released."""
    gate = None

    def status(self):
        return {"available": True, "device": "cpu"}

    def classes(self, model):
        return ["Pinna nobilis", "rock"]

    def run(self, params, emit, should_stop, set_total):
        pairs = sorted(p.stem for p in (Path(params["_folder"]) / "lx").iterdir())
        if not pairs:
            raise AppError("No stereo pair found: lx and rx must contain photos with the same names.", 422)
        set_total(len(pairs))
        for i, ts in enumerate(pairs):
            if self.gate is not None:
                self.gate.wait(5)
            if should_stop():
                return
            emit({"timestamp": ts, "detections": [{"track_id": "Pn-1", "label": "Pinna nobilis", "confidence": 0.9,
                                                    "length_mm": 100.0 + i, "width_mm": 40.0, "depth_mm": 800.0,
                                                    "contact_distance_mm": None, "bbox": [1, 2, 3, 4]}]},
                 JPEG, 1)


def _req(url, method="GET", token=None, data=None, raw=False, headers=None):
    body = None if data is None else (data if isinstance(data, bytes) else json.dumps(data).encode())
    r = urllib.request.Request(url, body, method=method, headers=dict(headers or {}))
    if token:
        r.add_header("Authorization", "Bearer " + token)
    if data is not None and not isinstance(data, bytes):
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=10) as res:
            out = res.read()
            return res.status, (out if raw else json.loads(out or b"null")), dict(res.headers)
    except urllib.error.HTTPError as e:
        out = e.read()
        try:
            return e.code, json.loads(out or b"null"), dict(e.headers)
        except ValueError:
            return e.code, out, dict(e.headers)


class WebServer:
    def __init__(self, engine=FakeEngine):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "srv"
        db = Database(self.data / "server.db")
        db.create_user("admin", "adminpass1", ROLE_SERVER)
        db.create_user("bob", "bobpass123")
        base = type("TestWeb", (WebHandler,), {"engine_factory": engine})
        self.httpd = make_server(self.data, "127.0.0.1", 0, admin_key="", handler_base=base)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def login(self, name, pw):
        return _req(self.url + "/api/login", "POST", data={"username": name, "password": pw})[1]["token"]

    def close(self):
        self.httpd.handler.jobs.shutdown()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()


class TestPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = WebServer()

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def test_index_and_assets(self):
        st, body, hd = _req(self.s.url + "/", raw=True)
        self.assertEqual(st, 200)
        self.assertIn(b"app.js", body)
        self.assertIn("default-src 'self'", hd["Content-Security-Policy"])
        self.assertEqual(hd["X-Frame-Options"], "DENY")
        st, body, hd = _req(self.s.url + "/app.js", raw=True)
        self.assertEqual(st, 200)
        self.assertTrue(hd["Content-Type"].startswith("text/javascript"))

    def test_unknown_page_gets_index_missing_file_404(self):
        st, body, _ = _req(self.s.url + "/library/stereo", raw=True)
        self.assertEqual(st, 200)
        self.assertIn(b"app.js", body)
        self.assertEqual(_req(self.s.url + "/nothing.js")[0], 404)

    def test_no_path_traversal(self):
        for p in ("/../server/db.py", "/%2e%2e/server/db.py", "/..%2f..%2fserver%2fdb.py"):
            st, body, _ = _req(self.s.url + p, raw=True)
            self.assertNotIn(b"sqlite3", body if isinstance(body, bytes) else b"", p)

    def test_base_api_still_works(self):
        st, body, _ = _req(self.s.url + "/api/health")
        self.assertEqual((st, body["ok"]), (200, True))
        self.assertEqual(_req(self.s.url + "/api/nothing", token=self.s.login("bob", "bobpass123"))[0], 404)

    def test_translations(self):
        st, body, _ = _req(self.s.url + "/api/i18n?lang=it")
        self.assertEqual(st, 200)
        self.assertEqual(body["strings"]["Library"], "Libreria")
        self.assertEqual(_req(self.s.url + "/api/i18n?lang=../../x")[0], 404)
        self.assertIn("Sign-in required.", load_strings("it"))      # server errors come from common/translations


class TestAnalysisRoutes(unittest.TestCase):
    def setUp(self):
        FakeEngine.gate = None
        self.s = WebServer()
        self.admin = self.s.login("admin", "adminpass1")
        self.bob = self.s.login("bob", "bobpass123")
        for side in ("lx", "rx"):
            for ts in ("1723130400", "1723130401"):
                self.upload(self.bob, f"cap/{side}/{ts}.png", png_bytes())
        self.upload(self.bob, "best.onnx", b"weights")

    def tearDown(self):
        FakeEngine.gate = None
        self.s.close()

    def upload(self, token, rel, data):
        st, body, _ = _req(f"{self.s.url}/api/files/upload?area=mine&path={rel}", "PUT", token, data)
        self.assertEqual(st, 201, body)

    def start(self, token=None, **kw):
        d = {"source": {"area": "mine", "path": "cap"}, "model": {"area": "mine", "path": "best.onnx"}}
        d.update(kw)
        return _req(self.s.url + "/api/analysis/jobs", "POST", token or self.bob, d)

    def wait(self, job_id, token=None):
        for _ in range(100):
            st, body, _ = _req(f"{self.s.url}/api/analysis/jobs/{job_id}", token=token or self.bob)
            if body["job"]["status"] not in ("queued", "running"):
                return body["job"]
            time.sleep(0.05)
        self.fail("job did not finish")

    def test_requires_sign_in(self):
        self.assertEqual(_req(self.s.url + "/api/analysis/status")[0], 401)
        self.assertEqual(_req(self.s.url + "/api/analysis/jobs", "POST", data={})[0], 401)

    def test_status_and_classes(self):
        st, body, _ = _req(self.s.url + "/api/analysis/status", token=self.bob)
        self.assertTrue(body["available"])
        self.assertEqual(body["defaults"]["baseline_mm"], 60.0)
        st, body, _ = _req(self.s.url + "/api/analysis/classes?area=mine&path=best.onnx", token=self.bob)
        self.assertEqual(body["classes"], ["Pinna nobilis", "rock"])
        st, body, _ = _req(self.s.url + "/api/analysis/classes?area=mine&path=cap", token=self.bob)
        self.assertEqual(st, 422)

    def test_full_job(self):
        st, body, _ = self.start(label="Pinna nobilis", baseline_mm=75, focal_length_px=1500)
        self.assertEqual(st, 201, body)
        job = self.wait(body["job"]["id"])
        self.assertEqual((job["status"], job["done"], job["total"]), ("done", 2, 2))
        self.assertEqual(job["results"][1]["detections"][0]["length_mm"], 101.0)
        self.assertNotIn("_folder", job)                             # server paths are never sent
        self.assertNotIn(self.s.tmp.name, json.dumps(job))
        st, part, _ = _req(f"{self.s.url}/api/analysis/jobs/{job['id']}?since=1", token=self.bob)
        self.assertEqual([r["index"] for r in part["job"]["results"]], [1])
        st, img, hd = _req(f"{self.s.url}/api/analysis/jobs/{job['id']}/overlay/0", token=self.bob, raw=True)
        self.assertEqual((st, img, hd["Content-Type"]), (200, JPEG, "image/jpeg"))
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{job['id']}/overlay/9", token=self.bob)[0], 404)
        st, csv_body, hd = _req(f"{self.s.url}/api/analysis/jobs/{job['id']}/csv", token=self.bob, raw=True)
        text = csv_body.decode()
        self.assertIn("=== STATISTICHE AGGREGATE PER ID ===", text)
        self.assertIn("Pn-1,Pinna nobilis,2,100.50,40.00,0.900", text)
        self.assertIn('filename="cap_analysis.csv"', hd["Content-Disposition"])
        st, lst, _ = _req(self.s.url + "/api/analysis/jobs", token=self.bob)
        self.assertEqual([j["id"] for j in lst["jobs"]], [job["id"]])

    def test_other_users_cannot_see_a_job(self):
        jid = self.start()[1]["job"]["id"]
        self.wait(jid)
        bob2 = self.s.login("admin", "adminpass1")
        Database(self.s.data / "server.db").create_user("carl", "carlpass12")
        carl = self.s.login("carl", "carlpass12")
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{jid}", token=carl)[0], 404)
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{jid}/csv", token=carl)[0], 404)
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{jid}", token=bob2)[0], 200)   # administrators can

    def test_cannot_read_another_users_folder(self):
        st, body, _ = self.start(token=self.admin)                       # "mine" is the admin's own folder: empty
        self.assertEqual(st, 404, body)

    def test_one_running_job_per_user_and_cancel(self):
        FakeEngine.gate = threading.Event()
        jid = self.start()[1]["job"]["id"]
        st, body, _ = self.start()
        self.assertEqual(st, 409)
        st, body, _ = _req(f"{self.s.url}/api/analysis/jobs/{jid}/cancel", "POST", self.bob)
        self.assertEqual(st, 200)
        FakeEngine.gate.set()
        self.assertEqual(self.wait(jid)["status"], "cancelled")
        self.assertEqual(self.start()[0], 201)                           # a new one can start now

    def test_delete(self):
        jid = self.start()[1]["job"]["id"]
        self.wait(jid)
        folder = self.s.data / "web_jobs" / jid
        self.assertTrue(folder.is_dir())
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{jid}", "DELETE", self.bob)[0], 200)
        self.assertFalse(folder.exists())
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{jid}", token=self.bob)[0], 404)

    def test_invalid_parameters(self):
        self.assertEqual(self.start(baseline_mm=-1)[0], 422)
        self.assertEqual(self.start(focal_length_px="x")[0], 422)
        self.assertEqual(self.start(model={"area": "mine", "path": "cap"})[0], 422)
        self.assertEqual(self.start(source={"area": "mine", "path": "../../.."})[0], 400)
        self.assertEqual(self.start(source="nope")[0], 422)

    def test_engine_error_is_reported(self):
        (self.s.data / "store" / "mine" / "bob" / "empty" / "lx").mkdir(parents=True)
        jid = self.start(source={"area": "mine", "path": "empty"})[1]["job"]["id"]
        job = self.wait(jid)
        self.assertEqual(job["status"], "error")
        self.assertIn("No stereo pair", job["error"])


class TestGroupAnalyses(unittest.TestCase):
    def setUp(self):
        self.s = WebServer()
        db = Database(self.s.data / "server.db")
        db.create_user("carl", "carlpass12")
        self.admin, self.bob, self.carl = (self.s.login(*c) for c in
                                           (("admin", "adminpass1"), ("bob", "bobpass123"), ("carl", "carlpass12")))
        st, body, _ = _req(self.s.url + "/api/groups", "POST", self.bob, {"name": "Lab A"})
        self.assertEqual(st, 201, body)                     # bob makes the group: he looks after it and writes in it
        for side in ("lx", "rx"):
            st, body, _ = _req(f"{self.s.url}/api/files/upload?area=groups&path=Lab%20A/cap/{side}/1.png", "PUT",
                               self.bob, png_bytes())
            self.assertEqual(st, 201, body)
        _req(f"{self.s.url}/api/files/upload?area=groups&path=Lab%20A/best.onnx", "PUT", self.bob, b"weights")

    def tearDown(self):
        self.s.close()

    def start(self, token, **kw):
        d = dict({"source": {"area": "groups", "path": "Lab A/cap"},
                  "model": {"area": "groups", "path": "Lab A/best.onnx"}}, **kw)
        return _req(self.s.url + "/api/analysis/jobs", "POST", token, d)

    def test_group_folder_and_shared_job(self):
        self.assertEqual(self.start(self.carl)[0], 404)                       # not in the group
        self.assertEqual(self.start(self.carl, group="Lab A")[0], 404)
        st, body, _ = self.start(self.bob, group="Lab A")
        self.assertEqual(st, 201, body)
        self.assertEqual(body["job"]["group"], "Lab A")
        jid = body["job"]["id"]
        _req(self.s.url + "/api/groups/members", "POST", self.bob, {"group": "Lab A", "username": "carl"})
        st, body, _ = _req(f"{self.s.url}/api/analysis/jobs/{jid}", token=self.carl)   # now a member: can read
        self.assertEqual(st, 200)
        self.assertEqual([j["id"] for j in _req(self.s.url + "/api/analysis/jobs", token=self.carl)[1]["jobs"]], [jid])
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{jid}", "DELETE", self.carl)[0], 404)   # but not delete
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{jid}/cancel", "POST", self.carl)[0], 404)

    def test_hidden_library_items_cannot_be_analysed(self):
        store = self.s.data / "store" / "library" / "stereo" / "Pinna nobilis" / "Pinna nobilis_bob_2026-01-01"
        for side in ("lx", "rx"):
            (store / side).mkdir(parents=True)
            (store / side / "IMG_0001.png").write_bytes(png_bytes())
        db = Database(self.s.data / "server.db")
        sid = db.add_submission("bob", "Pinna nobilis", "x", 2, kind="stereo", visibility="private")
        db.review_submission(sid, "approved", "admin", path="Pinna nobilis/Pinna nobilis_bob_2026-01-01")
        src = {"area": "stereo", "path": "Pinna nobilis/Pinna nobilis_bob_2026-01-01"}
        self.assertEqual(self.start(self.carl, source=src, model={"area": "mine", "path": "x.pt"})[0], 404)
        self.assertEqual(self.start(self.bob, source=src)[0], 201)


class TestUnavailable(unittest.TestCase):
    def test_without_libraries(self):
        class NoLibs(FakeEngine):
            def status(self):
                return {"available": False, "reason": "Missing library on the server: cv2"}
        s = WebServer(NoLibs)
        try:
            tok = s.login("bob", "bobpass123")
            st, body, _ = _req(s.url + "/api/analysis/status", token=tok)
            self.assertFalse(body["available"])
            st, body, _ = _req(s.url + "/api/analysis/jobs", "POST", tok,
                               {"source": {"area": "mine", "path": ""}, "model": {"area": "mine", "path": "x.pt"}})
            self.assertEqual(st, 503)
            self.assertIn("cv2", body["error"])
        finally:
            s.close()

    def test_real_engine_status_is_safe_without_libraries(self):
        st = AnalysisEngine.status()                    # in CI there is no OpenCV: it must not raise
        self.assertIn("available", st)


class TestWebIsolation(unittest.TestCase):
    def test_imports(self):
        """The web app joins the server and the analysis logic, nothing else: no Qt, no other section."""
        import ast
        root = Path(__file__).resolve().parent.parent
        for p in (root / "webapp").rglob("*.py"):
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                names = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                    [n.module] if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module else []
                for m in names:
                    self.assertNotIn(m.split(".")[0], ("PySide6", "PyQt5", "PyQt6"), f"{p}")
                    if m.startswith("corpse"):
                        self.assertTrue(m.startswith("corpse.functions.analysis"), f"{p} imports {m}")

    def test_server_does_not_import_the_web_app(self):
        root = Path(__file__).resolve().parent.parent
        for p in (root / "server").rglob("*.py"):
            self.assertNotIn("webapp", p.read_text(encoding="utf-8").replace("python -m webapp", ""), str(p))


class TestQueueAndReport(unittest.TestCase):
    def test_pruning_and_leftovers(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "old_job").mkdir()
            jm = JobManager(Path(d), FakeEngine(), per_user=1)
            self.assertFalse((Path(d) / "old_job").exists())               # leftovers of a previous run go away
            src = Path(d) / "src" / "lx"
            src.mkdir(parents=True)
            (src / "1.png").write_bytes(b"x")
            ids = []
            for _ in range(3):
                ids.append(jm.submit("bob", {"_folder": str(src.parent)})["id"])
                for _ in range(100):
                    if jm.get(ids[-1], "bob").status == "done":
                        break
                    time.sleep(0.02)
            self.assertEqual(len(jm.list("bob")), 2)                       # one kept + the newest
            jm.shutdown()

    def test_report_without_measures(self):
        from webapp.jobs import Job
        j = Job("x", "bob", {}, Path("."))
        j.results = [{"timestamp": "1", "detections": [{"track_id": None, "label": "rock", "confidence": 0.5,
                                                        "length_mm": None, "width_mm": None, "depth_mm": None}]}]
        text = report_csv(j)
        self.assertIn("N/D,rock,1,,,0.500", text)


if __name__ == "__main__":
    unittest.main()
