"""Security fixes: models loaded only from reviewed places, hidden library items never reachable through a parent folder
or an unnormalised path, accounts waiting for an administrator's approval (standard library only)."""
import importlib.util
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import quote

from common.params import ROLE_SERVER
from server.app import make_server
from server.db import Database
from webapp.handler import WebHandler

from tests.test_webapp_enhance import FakeEnhance
from tests.test_webapp import FakeEngine, _req
from tests.util import png_bytes

ITEM = "Pinna nobilis/Pinna nobilis_bob_2026-01-01"


class Recorder(FakeEnhance):
    """The fake enhancer, which also honours and remembers what the handler asks it to skip."""
    seen = []

    def run(self, params, emit, should_stop, set_total, progress=None):
        Recorder.seen.append(params)
        exclude = [Path(e) for e in params.get("_exclude") or ()]
        src, dst = Path(params["_source"]), Path(params["_output"])
        files = [p for p in sorted(src.rglob("*")) if p.is_file() and not any(p == e or e in p.parents for e in exclude)]
        set_total(len(files))
        for p in files:
            target = dst / p.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes())
            emit({"file": str(p.relative_to(src))}, None, 0)


class Base(unittest.TestCase):
    approve = False

    def setUp(self):
        Recorder.seen = []
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "srv"
        self.db = Database(self.data / "server.db")
        self.db.create_user("admin", "adminpass1", ROLE_SERVER)
        self.db.create_user("bob", "bobpass123")
        self.db.create_user("carl", "carlpass12")
        handler = type("W", (WebHandler,), {"engine_factory": FakeEngine, "enhance_factory": Recorder})
        self.httpd = make_server(self.data, "127.0.0.1", 0, admin_key="a-long-enough-admin-key",
                                 handler_base=handler, approve_register=self.approve)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def login(self, name, pw):
        st, body, _ = _req(self.url + "/api/login", "POST", data={"username": name, "password": pw})
        self.assertEqual(st, 200, body)
        return body["token"]

    def up(self, token, area, rel, data):
        st, body, _ = _req(f"{self.url}/api/files/upload?area={area}&path={quote(rel)}", "PUT", token, data)
        self.assertEqual(st, 201, body)
        return body

    def private_item(self, kind="stereo", area="stereo"):
        """An approved item of bob's, visible only to him (and the administrators)."""
        root = self.data / "store" / "library" / area / ITEM
        for side in ("lx", "rx"):
            (root / side).mkdir(parents=True)
            (root / side / "IMG_0001.png").write_bytes(png_bytes())
        (root / "lx" / "IMG_0001.txt").write_text("0 0.5 0.5 0.1 0.1\n")
        sid = self.db.add_submission("bob", "Pinna nobilis", "x", 2, kind=kind, visibility="private")
        self.db.review_submission(sid, "approved", "admin", path=ITEM)
        return root


class ModelsAreReviewed(Base):
    def setUp(self):
        super().setUp()
        self.bob = self.login("bob", "bobpass123")
        self.admin = self.login("admin", "adminpass1")
        for side in ("lx", "rx"):
            self.up(self.bob, "mine", f"cap/{side}/1.png", png_bytes())

    def classes(self, token, area, path):
        return _req(f"{self.url}/api/analysis/classes?area={area}&path={quote(path)}", token=token)

    def test_pt_from_personal_or_group_folder_is_never_loaded(self):
        self.up(self.bob, "mine", "evil.pt", b"pickle")
        self.assertEqual(self.classes(self.bob, "mine", "evil.pt")[0], 422)
        d = {"source": {"area": "mine", "path": "cap"}, "model": {"area": "mine", "path": "evil.pt"}}
        self.assertEqual(_req(self.url + "/api/analysis/jobs", "POST", self.bob, d)[0], 422)
        _req(self.url + "/api/groups", "POST", self.bob, {"name": "Lab A"})   # he makes it: he writes in it
        self.up(self.bob, "groups", "Lab A/evil.pt", b"pickle")
        self.assertEqual(self.classes(self.bob, "groups", "Lab A/evil.pt")[0], 422)
        # administrators too: the file may come from anyone
        self.assertEqual(self.classes(self.admin, "groups", "Lab A/evil.pt")[0], 422)

    def test_pending_pt_is_not_loaded_approved_one_is(self):
        body = self.up(self.bob, "models", "Pinna nobilis/new.pt", b"pickle")
        self.assertTrue(body["pending"])
        self.assertEqual(self.classes(self.admin, "models", body["path"])[0], 422)
        approved = self.data / "store" / "library" / "models" / "Pinna nobilis" / "best.pt"
        approved.parent.mkdir(parents=True)
        approved.write_bytes(b"reviewed")
        st, body, _ = self.classes(self.bob, "models", "Pinna nobilis/best.pt")
        self.assertEqual(st, 200, body)

    def test_onnx_from_personal_folder_still_works(self):
        self.up(self.bob, "mine", "m.onnx", b"onnx")
        self.assertEqual(self.classes(self.bob, "mine", "m.onnx")[0], 200)


class HiddenItems(Base):
    def setUp(self):
        super().setUp()
        self.root = self.private_item()
        self.bob = self.login("bob", "bobpass123")
        self.carl = self.login("carl", "carlpass12")

    def download(self, token, path):
        return _req(f"{self.url}/api/files/download?area=stereo&path={quote(path)}", token=token, raw=True)[0]

    def test_unnormalised_paths_do_not_bypass_visibility(self):
        self.assertEqual(self.download(self.bob, ITEM + "/lx/IMG_0001.png"), 200)
        for path in (ITEM + "/lx/IMG_0001.png", "Pinna nobilis//Pinna nobilis_bob_2026-01-01/lx/IMG_0001.png",
                     "Pinna nobilis/./Pinna nobilis_bob_2026-01-01/lx/IMG_0001.png",
                     "./" + ITEM + "/lx/IMG_0001.png", ITEM.replace("/", "\\") + "\\lx\\IMG_0001.png",
                     "/" + ITEM + "//lx/./IMG_0001.png"):
            self.assertEqual(self.download(self.carl, path), 404, path)

    def enhance(self, token, path):
        st, body, _ = _req(self.url + "/api/enhance/jobs", "POST", token,
                           {"method": "waternet", "source": {"area": "stereo", "path": path}})
        self.assertEqual(st, 201, body)
        jid = body["job"]["id"]
        for _ in range(100):
            job = _req(f"{self.url}/api/enhance/jobs/{jid}", token=token)[1]["job"]
            if job["status"] not in ("queued", "running"):
                return job
            time.sleep(0.05)
        self.fail("job did not finish")

    def test_enhancing_a_parent_folder_skips_hidden_items(self):
        other = self.data / "store" / "library" / "stereo" / "Pinna nobilis" / "public_one"
        (other / "lx").mkdir(parents=True)
        (other / "lx" / "a.png").write_bytes(png_bytes())
        for path in ("", "Pinna nobilis"):
            job = self.enhance(self.carl, path)
            self.assertEqual(job["status"], "done", job)
            names = [r["file"] for r in job["results"]]
            self.assertTrue(any("public_one" in n for n in names), names)
            self.assertFalse(any("bob" in n for n in names), names)
            out = self.data / "store" / "mine" / "carl" / job["output"]["path"]
            self.assertFalse([p for p in out.rglob("*") if "bob" in str(p)])
        self.assertTrue(Recorder.seen[-1]["_exclude"])
        # the owner gets everything
        job = self.enhance(self.bob, "Pinna nobilis")
        self.assertTrue(any("bob" in r["file"] for r in job["results"]))

    def test_analysis_of_a_folder_holding_hidden_items_is_refused(self):
        self.up(self.carl, "mine", "m.onnx", b"onnx")
        d = {"source": {"area": "stereo", "path": "Pinna nobilis"}, "model": {"area": "mine", "path": "m.onnx"}}
        self.assertEqual(_req(self.url + "/api/analysis/jobs", "POST", self.carl, d)[0], 422)


HAVE_CV = all(importlib.util.find_spec(m) for m in ("cv2", "torch", "numpy"))


@unittest.skipUnless(HAVE_CV, "OpenCV and PyTorch are not installed")
class RealEngineExclude(unittest.TestCase):
    def test_excluded_folders_are_not_read(self):
        import cv2
        import numpy as np
        from webapp.enhance import EnhanceEngine
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "lib"
            for name in ("open", "secret"):
                (src / name).mkdir(parents=True)
                cv2.imwrite(str(src / name / "1.png"), np.zeros((20, 20, 3), np.uint8))
                (src / name / "1.txt").write_text("0 0.5 0.5 0.1 0.1\n")
            rows = []
            EnhanceEngine().run({"method": "classical", "params": {"white_balance": False, "sharpen": 0.0, "clip_limit": 0.0},
                                 "_source": str(src), "_output": str(Path(d) / "out"), "_quota_root": d,
                                 "_quota_bytes": 1 << 30, "_exclude": [str(src / "secret")]},
                                lambda r, img, n: rows.append(r), lambda: False, lambda n: None)
            self.assertEqual([r["file"] for r in rows], ["open/1.png"])
            self.assertFalse((Path(d) / "out" / "secret").exists())


class Approval(Base):
    approve = True

    def register(self, name, key=None):
        d = {"username": name, "password": "password123"}
        if key:
            d["key"] = key
        return _req(self.url + "/api/register", "POST", data=d)

    def test_new_accounts_wait_for_an_administrator(self):
        self.assertTrue(_req(self.url + "/api/health")[1]["approval"])
        st, body, _ = self.register("newbie")
        self.assertEqual(st, 201, body)
        self.assertTrue(body["user"]["pending"])
        self.assertFalse(body["user"]["active"])
        st, body, _ = _req(self.url + "/api/login", "POST", data={"username": "newbie", "password": "password123"})
        self.assertEqual(st, 403)
        self.assertIn("approval", body["error"])
        st, body, _ = _req(self.url + "/api/login", "POST", data={"username": "newbie", "password": "wrong-pass"})
        self.assertNotIn("approval", body.get("error", ""))           # the wrong password learns nothing more
        admin = self.login("admin", "adminpass1")
        uid = next(u["id"] for u in _req(self.url + "/api/users", token=admin)[1]["users"] if u["username"] == "newbie")
        st, body, _ = _req(f"{self.url}/api/users/{uid}", "PATCH", admin, {"active": True})
        self.assertEqual(st, 200, body)
        self.assertFalse(body["user"]["pending"])
        self.login("newbie", "password123")

    def test_admin_key_registration_is_not_held(self):
        st, body, _ = self.register("boss1", key="a-long-enough-admin-key")
        self.assertEqual(st, 201, body)
        self.assertFalse(body["user"]["pending"])
        self.login("boss1", "password123")

    def test_disabled_later_is_not_pending(self):
        admin = self.login("admin", "adminpass1")
        uid = next(u["id"] for u in _req(self.url + "/api/users", token=admin)[1]["users"] if u["username"] == "bob")
        _req(f"{self.url}/api/users/{uid}", "PATCH", admin, {"active": False})
        st, body, _ = _req(self.url + "/api/login", "POST", data={"username": "bob", "password": "bobpass123"})
        self.assertEqual((st, body["error"]), (403, "Account disabled."))


class NoApproval(Base):
    def test_default_server_keeps_open_registration(self):
        st, body, _ = _req(self.url + "/api/register", "POST", data={"username": "free1", "password": "password123"})
        self.assertFalse(body["user"]["pending"])
        self.login("free1", "password123")


if __name__ == "__main__":
    unittest.main()
