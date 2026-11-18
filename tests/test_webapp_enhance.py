"""Image enhancement in the web app: where results go, who may use what, previews; with a fake engine (standard
library only). The real nautilus engine is tested too when OpenCV and PyTorch are installed.

Autore: Magform
"""
import importlib.util
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from common.errors import AppError
from server.db import Database
from webapp.enhance import EnhanceEngine, output_name

from tests.test_webapp import FakeEngine, WebServer, _req
from tests.util import png_bytes

METHODS = {"waternet": {"sharpen": 0.1}, "fusion": {"red": 1.0}}


class FakeEnhance:
    """Copies the media to the output (same names), as the real engine does after enhancing them."""
    def status(self):
        return {"available": True, "device": "cpu", "gpu": False, "video": True,
                "methods": [{"id": k, "available": True, "params": []} for k in METHODS]}

    def check_method(self, method, params):
        if method not in METHODS:
            raise AppError("Unknown enhancement method.", 422)
        return {"method": method, "params": dict(METHODS[method], **(params or {}))}

    def preview(self, path, methods, seconds=0.0):
        return {"original": {"image": "data:,", "metrics": {}}, "seconds": seconds,
                "results": [{"id": m["id"], "image": "data:,"} for m in methods]}

    def enhance_image(self, image, method):
        return image

    def run(self, params, emit, should_stop, set_total, progress=None):
        src, dst = Path(params["_source"]), Path(params["_output"])
        files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
        set_total(len(files))
        for p in files:
            target = dst if src.is_file() else dst / p.relative_to(src).parent / output_name(p)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
            emit({"file": p.name, "output": target.name}, None, 0)


class EnhanceRoutes(unittest.TestCase):
    def setUp(self):
        self.s = WebServer.__new__(WebServer)
        self._start()
        self.bob = self.s.login("bob", "bobpass123")
        self.admin = self.s.login("admin", "adminpass1")
        for side in ("lx", "rx"):
            self.up(self.bob, "mine", f"cap/{side}/1.png", png_bytes())
        self.up(self.bob, "mine", "cap/lx/1.txt", b"0 0.5 0.5 0.1 0.1\n")

    def _start(self):
        import threading
        from server.app import make_server
        from webapp.handler import WebHandler
        s = self.s
        s.tmp = tempfile.TemporaryDirectory()
        s.data = Path(s.tmp.name) / "srv"
        db = Database(s.data / "server.db")
        db.create_user("admin", "adminpass1", "server")
        db.create_user("bob", "bobpass123")
        db.create_user("carl", "carlpass12")
        handler = type("W", (WebHandler,), {"engine_factory": FakeEngine, "enhance_factory": FakeEnhance})
        s.httpd = make_server(s.data, "127.0.0.1", 0, admin_key="", handler_base=handler)
        s.url = f"http://127.0.0.1:{s.httpd.server_address[1]}"
        threading.Thread(target=s.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.s.close()

    def up(self, token, area, rel, data):
        st, body, _ = _req(f"{self.s.url}/api/files/upload?area={area}&path={rel.replace(' ', '%20')}", "PUT", token, data)
        self.assertEqual(st, 201, body)

    def start(self, token, source, method="waternet", **kw):
        return _req(self.s.url + "/api/enhance/jobs", "POST", token, dict({"source": source, "method": method}, **kw))

    def wait(self, jid, token):
        for _ in range(100):
            job = _req(f"{self.s.url}/api/enhance/jobs/{jid}", token=token)[1]["job"]
            if job["status"] not in ("queued", "running"):
                return job
            time.sleep(0.05)
        self.fail("job did not finish")

    def mine(self, user="bob"):
        return self.s.data / "store" / "mine" / user

    def test_folder_next_to_the_original(self):
        st, body, _ = self.start(self.bob, {"area": "mine", "path": "cap"}, params={"sharpen": 0.3})
        self.assertEqual(st, 201, body)
        self.assertEqual(body["job"]["output"], {"area": "mine", "path": "cap_waternet"})
        self.assertEqual(body["job"]["params"], {"sharpen": 0.3})
        self.assertNotIn("_source", body["job"])
        job = self.wait(body["job"]["id"], self.bob)
        self.assertEqual((job["status"], job["done"]), ("done", 3))
        self.assertTrue((self.mine() / "cap_waternet" / "lx" / "1.png").is_file())
        self.assertTrue((self.mine() / "cap_waternet" / "rx" / "1.png").is_file())
        # a second run does not overwrite the first
        st, body, _ = self.start(self.bob, {"area": "mine", "path": "cap"})
        self.assertEqual(body["job"]["output"]["path"], "cap_waternet_2")

    def test_single_file(self):
        st, body, _ = self.start(self.bob, {"area": "mine", "path": "cap/lx/1.png"}, method="fusion")
        self.assertEqual(body["job"]["output"], {"area": "mine", "path": "cap/lx/1_fusion.png"})
        self.wait(body["job"]["id"], self.bob)
        self.assertTrue((self.mine() / "cap" / "lx" / "1_fusion.png").is_file())
        st, body, _ = self.start(self.bob, {"area": "mine", "path": "cap/lx/1.txt"})
        self.assertEqual(st, 422)

    def test_group_folder_and_library(self):
        st, body, _ = _req(self.s.url + "/api/groups", "POST", self.bob, {"name": "Lab A"})
        self.up(self.bob, "groups", "Lab A/dive/a.png", png_bytes())
        st, body, _ = self.start(self.bob, {"area": "groups", "path": "Lab A/dive"})
        self.assertEqual(body["job"]["output"], {"area": "groups", "path": "Lab A/dive_waternet"})
        self.assertEqual(self.start(self.bob, {"area": "groups", "path": "Lab A"})[0], 422)      # not the group root
        carl = self.s.login("carl", "carlpass12")
        self.assertEqual(self.start(carl, {"area": "groups", "path": "Lab A/dive"})[0], 404)
        # a library item (read-only) goes to the user's own folder
        lib = self.s.data / "store" / "library" / "photos" / "Pinna nobilis" / "Pinna nobilis_x_2026-01-01"
        lib.mkdir(parents=True)
        (lib / "IMG_0001.png").write_bytes(png_bytes())
        st, body, _ = self.start(carl, {"area": "photos", "path": "Pinna nobilis/Pinna nobilis_x_2026-01-01"})
        self.assertEqual(body["job"]["output"], {"area": "mine", "path": "Pinna nobilis_x_2026-01-01_waternet"})

    def test_rejected_inputs(self):
        self.assertEqual(self.start(self.bob, {"area": "mine", "path": ""})[0], 422)               # the whole folder
        self.assertEqual(self.start(self.bob, {"area": "mine", "path": "cap"}, method="magic")[0], 422)
        self.assertEqual(self.start(self.bob, {"area": "mine", "path": "nothing"})[0], 404)
        self.assertEqual(self.start(self.bob, {"area": "mine", "path": "../admin"})[0], 400)
        self.assertEqual(_req(self.s.url + "/api/enhance/status")[0], 401)

    def test_preview_and_separate_lists(self):
        st, body, _ = _req(self.s.url + "/api/enhance/preview", "POST", self.bob,
                           {"source": {"area": "mine", "path": "cap/lx/1.png"}, "methods": [{"id": "fusion"}]})
        self.assertEqual((st, [r["id"] for r in body["results"]]), (200, ["fusion"]))
        self.assertEqual(_req(self.s.url + "/api/enhance/preview", "POST", self.bob,
                              {"source": {"area": "mine", "path": "cap"}, "methods": []})[0], 422)
        jid = self.start(self.bob, {"area": "mine", "path": "cap"})[1]["job"]["id"]
        self.wait(jid, self.bob)
        self.assertEqual([j["id"] for j in _req(self.s.url + "/api/enhance/jobs", token=self.bob)[1]["jobs"]], [jid])
        self.assertEqual(_req(self.s.url + "/api/analysis/jobs", token=self.bob)[1]["jobs"], [])
        self.assertEqual(_req(f"{self.s.url}/api/analysis/jobs/{jid}", token=self.bob)[0], 404)

    def test_enhance_before_analysis(self):
        self.up(self.bob, "mine", "best.onnx", b"w")
        d = {"source": {"area": "mine", "path": "cap"}, "model": {"area": "mine", "path": "best.onnx"}}
        self.assertEqual(_req(self.s.url + "/api/analysis/jobs", "POST", self.bob, dict(d, enhance={"method": "magic"}))[0], 422)
        st, body, _ = _req(self.s.url + "/api/analysis/jobs", "POST", self.bob, dict(d, enhance={"method": "fusion"}))
        self.assertEqual(st, 201, body)
        self.assertEqual(body["job"]["enhance"], {"method": "fusion", "params": {"red": 1.0}})


HAVE_LIBS = all(importlib.util.find_spec(m) for m in ("cv2", "torch", "numpy"))


@unittest.skipUnless(HAVE_LIBS, "OpenCV and PyTorch are not installed")
class RealEngine(unittest.TestCase):
    def test_folder_with_labels(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "cap", Path(d) / "out"
            for side in ("lx", "rx"):
                (src / side).mkdir(parents=True)
                img = np.full((60, 80, 3), (120, 90, 30), np.uint8)
                cv2.imwrite(str(src / side / "1.jpg"), img)
            (src / "lx" / "1.txt").write_text("0 0.5 0.5 0.2 0.2\n")
            rows = []
            EnhanceEngine().run({"method": "classical", "params": {"white_balance": True, "sharpen": 0.0, "clip_limit": 2.0},
                                 "_source": str(src), "_output": str(dst), "_quota_root": d, "_quota_bytes": 1 << 30},
                                lambda r, img, n: rows.append(r), lambda: False, lambda n: None)
            self.assertEqual(sorted(r["output"] for r in rows), ["lx/1.jpg", "rx/1.jpg"])
            self.assertEqual((dst / "lx" / "1.txt").read_text(), "0 0.5 0.5 0.2 0.2\n")
            self.assertEqual(cv2.imread(str(dst / "rx" / "1.jpg")).shape, (60, 80, 3))

    def test_quota(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "a.png"
            cv2.imwrite(str(src), np.zeros((50, 50, 3), np.uint8))
            with self.assertRaises(AppError):
                EnhanceEngine().run({"method": "classical", "params": {"white_balance": False, "sharpen": 0.0, "clip_limit": 0.0},
                                     "_source": str(src), "_output": str(Path(d) / "b.png"), "_quota_root": d,
                                     "_quota_bytes": 10}, lambda *a: None, lambda: False, lambda n: None)
