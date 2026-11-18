"""Who sees what in the library: everybody, the uploader and one work group, or the uploader only.

Here are also the quota of the folder of a group and the submissions a group shares with its members. The roles,
the approvals and the folder of a group itself are tested in test_groups.py. Standard library only.

Autore: Magform
Autore: Samuele Gallo
"""
import json
import unittest
import urllib.error
import urllib.parse
import urllib.request

from server.db import Database

from tests.util import TestServer, png_bytes

SPECIES = "Pinna nobilis"
GROUP = "Lab A"


class VisibilityTest(unittest.TestCase):
    def setUp(self):
        self.s = TestServer()
        db = Database(self.s.data / "server.db")
        for name in ("ann", "bob", "carl"):
            db.create_user(name, name + "pass123")
        self.admin = self.login("admin", "adminpass1")
        self.ann, self.bob, self.carl = (self.login(n, n + "pass123") for n in ("ann", "bob", "carl"))
        st, body = self.req("POST", "/api/groups", self.ann, {"name": GROUP})      # ann makes it: she looks after it
        self.assertEqual(st, 201, body)
        self.assertEqual(self.req("POST", "/api/groups/members", self.ann,
                                  {"group": GROUP, "username": "bob"})[0], 200)
        # the members write straight into the folder: here the waiting room is not what is being tested
        self.assertEqual(self.req("POST", "/api/groups/settings", self.ann,
                                  {"name": GROUP, "free_upload": True})[0], 200)

    def tearDown(self):
        self.s.close()

    # ---- helpers -------------------------------------------------------------------
    def req(self, method, path, token=None, data=None, raw=None, query=None):
        url = self.s.url + path + ("?" + urllib.parse.urlencode(query) if query else "")
        body = raw if raw is not None else (None if data is None else json.dumps(data).encode())
        r = urllib.request.Request(url, body, method=method)
        if token:
            r.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(r, timeout=10) as res:
                out = res.read()
                return res.status, (json.loads(out) if res.headers.get_content_type() == "application/json" and out else out)
        except urllib.error.HTTPError as e:
            out = e.read()
            try:
                return e.code, json.loads(out)
            except ValueError:
                return e.code, out

    def login(self, name, pw):
        return self.req("POST", "/api/login", data={"username": name, "password": pw})[1]["token"]

    def upload(self, token, area, path, data=b"x"):
        return self.req("PUT", "/api/files/upload", token, raw=data, query={"area": area, "path": path})

    def files(self, token, area, path=""):
        return self.req("GET", "/api/files", token, query={"area": area, "path": path})

    def group(self, token=None):
        groups = self.req("GET", "/api/groups", token or self.ann)[1]["groups"]
        return [g for g in groups if g["name"] == GROUP][0]

    def publish_stereo(self, token, species=SPECIES, **share):
        """Uploads a stereo pair, sends it, and has the admin approve it. Returns (id, approved path)."""
        for side in ("lx", "rx"):
            st, body = self.upload(token, "stereo", f"{species}/{side}/a.png", png_bytes())
            self.assertEqual(st, 201, body)
        st, body = self.req("POST", "/api/species/submit", token, dict({"species": species, "kind": "stereo"}, **share))
        self.assertEqual(st, 201, body)
        st, body = self.req("POST", f"/api/species/submissions/{body['id']}/approve", self.admin)
        self.assertEqual(st, 200, body)
        return body["id"], f"{species}/{body['folder']}"

    def catalog(self, token):
        return [i["path"] for i in self.req("GET", "/api/catalog", token, query={"kind": "stereo"})[1]["items"]]

    # ---- visibility -------------------------------------------------------------------
    def test_what_is_shared_with_a_group_is_seen_by_its_members_only(self):
        sid, path = self.publish_stereo(self.ann, visibility="group", vis_group=GROUP)
        self.assertIn(path, self.catalog(self.bob))
        self.assertNotIn(path, self.catalog(self.carl))
        item = [i for i in self.req("GET", "/api/catalog", self.bob, query={"kind": "stereo"})[1]["items"]
                if i["path"] == path][0]
        self.assertEqual((item["visibility"], item["vis_group"]), ("group", GROUP))
        # browsing: the species folder holds only this item, so it disappears for carl
        self.assertEqual(self.files(self.carl, "stereo")[1]["entries"], [])
        self.assertEqual([e["name"] for e in self.files(self.bob, "stereo")[1]["entries"]], [SPECIES])
        self.assertEqual(self.files(self.carl, "stereo", path)[1]["entries"], [])   # the content is filtered too
        q = {"area": "stereo", "path": path + "/lx/IMG_0001.png"}
        self.assertEqual(self.req("GET", "/api/files/download", self.carl, query=q)[0], 404)
        self.assertEqual(self.req("GET", "/api/files/download", self.bob, query=q)[0], 200)
        # the uploader opens it to everyone
        self.assertEqual(self.req("PATCH", f"/api/species/submissions/{sid}", self.carl, {"visibility": "public"})[0], 404)
        self.assertEqual(self.req("PATCH", f"/api/species/submissions/{sid}", self.ann, {"visibility": "public"})[0], 200)
        self.assertIn(path, self.catalog(self.carl))
        self.assertEqual(self.req("GET", "/api/files/download", self.carl, query=q)[0], 200)

    def test_private_and_mixed_species_folder(self):
        _, private = self.publish_stereo(self.ann, visibility="private")
        _, public = self.publish_stereo(self.carl)                                  # default: everyone
        self.assertEqual(sorted(self.catalog(self.bob)), [public])
        self.assertEqual(sorted(self.catalog(self.ann)), sorted([private, public]))
        self.assertEqual(sorted(self.catalog(self.admin)), sorted([private, public]))
        entries = [e["name"] for e in self.files(self.bob, "stereo", SPECIES)[1]["entries"]]
        self.assertEqual(entries, [public.split("/")[1]])                           # the species stays: one is public

    def test_a_sharing_that_makes_no_sense_is_refused(self):
        for side in ("lx", "rx"):
            self.upload(self.carl, "stereo", f"{SPECIES}/{side}/a.png", png_bytes())
        base = {"species": SPECIES, "kind": "stereo"}
        self.assertEqual(self.req("POST", "/api/species/submit", self.carl, dict(base, visibility="group"))[0], 422)
        self.assertEqual(self.req("POST", "/api/species/submit", self.carl, dict(base, visibility="secret"))[0], 422)
        self.assertEqual(self.req("POST", "/api/species/submit", self.carl,
                                  dict(base, visibility="group", vis_group=GROUP))[0], 404)     # not his group

    def test_the_members_see_the_submissions_shared_with_the_group(self):
        self.publish_stereo(self.ann, visibility="group", vis_group=GROUP)
        mine = self.req("GET", "/api/species/submissions", self.bob)[1]["submissions"]
        self.assertEqual(mine, [])                                                  # default: own uploads only
        shared = self.req("GET", "/api/species/submissions", self.bob, query={"include": "groups"})[1]["submissions"]
        self.assertEqual([(s["username"], s["vis_group"]) for s in shared], [("ann", GROUP)])
        self.assertEqual(self.req("GET", "/api/species/submissions", self.carl,
                                  query={"include": "groups"})[1]["submissions"], [])

    def test_deleting_a_group_keeps_what_was_shared_with_the_uploader(self):
        self.upload(self.bob, "groups", f"{GROUP}/notes.md", b"hi")
        _, path = self.publish_stereo(self.ann, visibility="group", vis_group=GROUP)
        self.assertEqual(self.req("POST", "/api/groups/delete", self.bob, {"name": GROUP})[0], 403)
        self.assertEqual(self.req("POST", "/api/groups/delete", self.ann, {"name": GROUP, "files": True})[0], 200)
        self.assertFalse((self.s.data / "store" / "groups" / GROUP).exists())
        self.assertNotIn(path, self.catalog(self.bob))                              # it became private, not public
        self.assertIn(path, self.catalog(self.ann))
        self.assertEqual(self.files(self.bob, "groups", GROUP)[0], 404)

    # ---- quota --------------------------------------------------------------------
    def test_the_quota_of_the_folder_of_a_group(self):
        self.assertEqual(self.req("POST", "/api/groups/quota", self.ann, {"name": GROUP, "quota_mb": 1})[0], 403)
        self.assertEqual(self.req("POST", "/api/groups/quota", self.admin, {"name": GROUP, "quota_mb": 1})[0], 200)
        self.assertEqual(self.upload(self.bob, "groups", f"{GROUP}/big.zip", b"x" * (2 << 20))[0], 413)
        self.assertEqual(self.upload(self.bob, "groups", f"{GROUP}/small.zip", b"x" * 1000)[0], 201)
        self.assertEqual(self.group(self.bob)["usage"], 1000)


if __name__ == "__main__":
    unittest.main()
