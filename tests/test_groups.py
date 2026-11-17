"""Work groups: anybody can make one and looks after it, the members send and the administrators approve."""
import tempfile
import unittest
from pathlib import Path

from corpse.functions.users.api import ApiClient, ApiError
from tests.util import TestServer, png_bytes


class OldDatabaseTest(unittest.TestCase):
    """A server that has been running since before the roles existed must keep working after the update."""

    def test_the_columns_are_added_and_the_maker_becomes_administrator(self):
        import sqlite3
        from server.db import Database
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            con = sqlite3.connect(path)
            con.executescript("""
                CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT, created REAL);
                CREATE TABLE groups(name TEXT PRIMARY KEY COLLATE NOCASE, created REAL NOT NULL,
                                    created_by TEXT NOT NULL DEFAULT '');
                CREATE TABLE group_members(group_name TEXT NOT NULL COLLATE NOCASE,
                                           username TEXT NOT NULL COLLATE NOCASE, added REAL NOT NULL,
                                           PRIMARY KEY(group_name, username));
                INSERT INTO groups VALUES('Dive', 1.0, 'mario');
                INSERT INTO group_members VALUES('Dive','mario',1.0);
                INSERT INTO group_members VALUES('Dive','luca',1.0);
            """)
            con.commit()
            con.close()
            db = Database(path)
            self.assertEqual(db.group_members("Dive"), [{"username": "mario", "role": "admin"},
                                                        {"username": "luca", "role": "member"}])
            self.assertEqual(db.admin_groups("mario"), ["Dive"])
            self.assertEqual(db.group("Dive")["description"], "")
            self.assertFalse(db.group_free_upload("Dive"))

    def test_a_group_whose_maker_had_left_keeps_its_members(self):
        import sqlite3
        from server.db import Database
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            con = sqlite3.connect(path)
            con.executescript("""
                CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT, created REAL);
                CREATE TABLE groups(name TEXT PRIMARY KEY COLLATE NOCASE, created REAL NOT NULL,
                                    created_by TEXT NOT NULL DEFAULT '');
                CREATE TABLE group_members(group_name TEXT NOT NULL COLLATE NOCASE,
                                           username TEXT NOT NULL COLLATE NOCASE, added REAL NOT NULL,
                                           PRIMARY KEY(group_name, username));
                INSERT INTO groups VALUES('Old', 1.0, 'gone');
                INSERT INTO group_members VALUES('Old','luca',1.0);
            """)
            con.commit()
            con.close()
            db = Database(path)
            members = {m["username"]: m["role"] for m in db.group_members("Old")}
            self.assertEqual(members, {"gone": "admin", "luca": "member"})


class GroupsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = TestServer()
        cls.tmp = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        cls.srv.close()

    def user(self, name):
        c = ApiClient(self.srv.url)
        c.register(name, "password123")
        c.login(name, "password123")
        return c

    def admin(self):
        c = ApiClient(self.srv.url)
        c.login("admin", "adminpass1")
        return c

    def put(self, client, rel, data=b"hello"):
        f = self.tmp / "up.bin"
        f.write_bytes(data)
        return client.upload("groups", rel, f)

    def group(self, name, owner="go"):
        """A group with its maker (administrator) and one plain member."""
        boss, member = self.user(f"{owner}1{name}"), self.user(f"{owner}2{name}")
        boss.create_group(name)
        boss.set_member(name, f"{owner}2{name}")
        return boss, member

    # ---- who makes a group ---------------------------------------------
    def test_whoever_makes_a_group_looks_after_it(self):
        u = self.user("gm1")
        group = u.create_group("Nautilus")
        self.assertEqual(group["members"], [{"username": "gm1", "role": "admin"}])
        self.assertEqual([g["role"] for g in u.groups()], ["admin"])

    def test_a_name_is_checked_and_unique(self):
        u = self.user("gm2")
        u.create_group("Team A")
        for bad in ("", "x", "a/b", "../etc"):
            with self.assertRaises(ApiError, msg=bad):
                u.create_group(bad)
        with self.assertRaises(ApiError) as e:
            u.create_group("team a")                               # same name, other case
        self.assertEqual(e.exception.status, 409)

    def test_only_the_groups_you_belong_to(self):
        boss, member = self.group("Hidden", "gh")
        stranger = self.user("gm3")
        self.assertEqual([g["name"] for g in member.groups()], ["Hidden"])
        self.assertEqual(stranger.groups(), [])
        self.assertIn("Hidden", [g["name"] for g in self.admin().groups(everyone=True)])

    # ---- roles ----------------------------------------------------------
    def test_an_administrator_promotes_and_demotes(self):
        boss, member = self.group("Crew", "gc")
        self.assertEqual(member.groups()[0]["role"], "member")
        boss.set_group_role("Crew", "gc2Crew", "admin")
        self.assertEqual(member.groups()[0]["role"], "admin")
        member.set_group_role("Crew", "gc1Crew", "member")          # now they can demote the other one too
        self.assertEqual(boss.groups()[0]["role"], "member")

    def test_a_plain_member_cannot_look_after_the_group(self):
        boss, member = self.group("Closed", "gk")
        stranger = self.user("gk3")
        for call in (lambda: member.set_member("Closed", "gk3"),
                     lambda: member.set_group_role("Closed", "gk1Closed", "member"),
                     lambda: member.delete_group("Closed"),
                     lambda: member.group_pending("Closed"),
                     lambda: stranger.group_pending("Closed")):
            with self.assertRaises(ApiError) as e:
                call()
            self.assertEqual(e.exception.status, 403)

    def test_a_group_never_runs_out_of_administrators(self):
        boss, member = self.group("Alone", "ga")
        for call in (lambda: boss.set_group_role("Alone", "ga1Alone", "member"),
                     lambda: boss.leave_group("Alone"),
                     lambda: boss.set_member("Alone", "ga1Alone", False)):
            with self.assertRaises(ApiError) as e:
                call()
            self.assertEqual(e.exception.status, 409)
        self.assertEqual(member.leave_group("Alone"), [{"username": "ga1Alone", "role": "admin"}])

    # ---- the files ------------------------------------------------------
    def test_an_administrator_of_the_group_writes_straight_away(self):
        boss, _member = self.group("Fast", "gf")
        res = self.put(boss, "Fast/notes.md", b"# dive\n")
        self.assertFalse(res.get("pending"))
        self.assertEqual([e["name"] for e in boss.list("groups", "Fast")], ["notes.md"])

    def test_what_a_member_sends_waits_for_an_administrator(self):
        boss, member = self.group("Wait", "gw")
        res = self.put(member, "Wait/photo.png", png_bytes())
        self.assertTrue(res["pending"])
        self.assertEqual(boss.list("groups", "Wait"), [])             # not in the group's folder yet
        waiting = boss.group_pending("Wait")
        self.assertEqual([(w["sender"], w["path"]) for w in waiting], [("gw2Wait", "photo.png")])
        self.assertEqual(boss.approve_group_upload(waiting[0]["logical"]), ["Wait/photo.png"])
        self.assertEqual([e["name"] for e in member.list("groups", "Wait")], ["photo.png"])
        self.assertEqual(boss.group_pending("Wait"), [])

    def test_a_refused_upload_disappears(self):
        boss, member = self.group("No", "gn")
        self.put(member, "No/bad.png", png_bytes())
        waiting = boss.group_pending("No")
        boss.reject_group_upload(waiting[0]["logical"])
        self.assertEqual(boss.group_pending("No"), [])
        self.assertEqual(boss.list("groups", "No"), [])

    def test_a_member_sees_their_own_upload_waiting_but_not_the_others(self):
        boss, member = self.group("Mine", "gq")
        other = self.user("gq3")
        boss.set_member("Mine", "gq3")
        self.put(member, "Mine/a.png", png_bytes())
        self.assertEqual([e["name"] for e in member.list("groups", "_pending/Mine/gq2Mine")], ["a.png"])
        with self.assertRaises(ApiError) as e:
            other.list("groups", "_pending/Mine/gq2Mine")
        self.assertEqual(e.exception.status, 403)

    def test_nothing_in_the_group_is_ever_overwritten(self):
        boss, member = self.group("Keep", "gp")
        self.put(boss, "Keep/a.txt", b"first")
        self.put(member, "Keep/a.txt", b"second")
        waiting = boss.group_pending("Keep")
        self.assertEqual(boss.approve_group_upload(waiting[0]["logical"]), ["Keep/a (2).txt"])
        self.assertEqual(boss.read_bytes("groups", "Keep/a.txt"), b"first")
        self.assertEqual(boss.read_bytes("groups", "Keep/a (2).txt"), b"second")

    def test_the_others_are_shut_out_of_the_folder(self):
        boss, _member = self.group("Shut", "gs")
        outside = self.user("gs3")
        self.put(boss, "Shut/notes.md")
        for call in (lambda: outside.list("groups", "Shut"),
                     lambda: outside.read_bytes("groups", "Shut/notes.md"),
                     lambda: self.put(outside, "Shut/mine.md")):
            with self.assertRaises(ApiError) as e:
                call()
            self.assertEqual(e.exception.status, 403)

    def test_the_root_shows_only_my_groups_and_everything_to_a_server_admin(self):
        boss, member = self.group("Alpha", "gr")
        boss.create_group("Beta")
        self.assertEqual([e["name"] for e in member.list("groups", "")], ["Alpha"])
        self.assertLessEqual({"Alpha", "Beta"}, {e["name"] for e in self.admin().list("groups", "")})

    def test_an_administrator_of_the_group_may_also_change_and_delete(self):
        boss, _member = self.group("Work", "gx")
        self.put(boss, "Work/a.png", png_bytes())
        boss.move("groups", "Work/a.png", "Work/b.png")
        self.assertEqual([e["name"] for e in boss.list("groups", "Work")], ["b.png"])
        boss.delete("groups", "Work/b.png")
        self.assertEqual(boss.list("groups", "Work"), [])

    def test_deleting_a_group_closes_the_door_but_keeps_the_files(self):
        boss, member = self.group("Gone", "gg")
        self.put(boss, "Gone/keep.md")
        boss.delete_group("Gone")
        self.assertEqual(member.groups(), [])
        with self.assertRaises(ApiError):
            member.list("groups", "Gone")
        self.assertEqual([e["name"] for e in self.admin().list("groups", "Gone")], ["keep.md"])


    # ---- settings of a group -------------------------------------------
    def test_the_settings_are_kept_and_only_an_administrator_changes_them(self):
        boss, member = self.group("Set", "gz")
        updated = boss.update_group("Set", description="Immersioni 2026", free_upload=True)
        self.assertEqual((updated["description"], updated["free_upload"]), ("Immersioni 2026", True))
        self.assertEqual(member.groups()[0]["description"], "Immersioni 2026")
        with self.assertRaises(ApiError) as e:
            member.update_group("Set", description="mia")
        self.assertEqual(e.exception.status, 403)

    def test_with_free_upload_a_member_writes_straight_into_the_group(self):
        boss, member = self.group("Free", "gy")
        self.assertTrue(self.put(member, "Free/a.txt")["pending"])        # before: it waits
        boss.update_group("Free", free_upload=True)
        res = self.put(member, "Free/b.txt")
        self.assertFalse(res.get("pending"))
        self.assertIn("b.txt", [e["name"] for e in member.list("groups", "Free")])

    def test_deleting_a_group_can_take_its_files_too(self):
        boss, _member = self.group("Wipe", "gu")
        self.put(boss, "Wipe/keep.md")
        boss.delete_group("Wipe", files=True)
        admin = self.admin()
        with self.assertRaises(ApiError) as e:
            admin.list("groups", "Wipe")
        self.assertEqual(e.exception.status, 404)


    # ---- publishing on the server in the name of the group ---------------
    def photo(self, client, rel):
        f = self.tmp / "p.png"
        f.write_bytes(png_bytes())
        return client.upload("photos", rel, f)

    def test_a_member_publishes_photos_for_the_group(self):
        boss, member = self.group("Pub", "gpb")
        admin = self.admin()
        self.photo(member, "Pinna nobilis/a.png")
        res = member.submit_species("Pinna nobilis", "photos", "Pub")
        self.assertEqual(res["group"], "Pub")
        admin.approve_submission(res["id"])
        item = [i for i in member.catalog("photos") if i["sent_by"] == "gpb2Pub"][0]
        self.assertEqual((item["uploader"], item["group"]), ("Pub", "Pub"))     # the group signs it
        self.assertTrue(item["path"].endswith("Pinna nobilis_Pub_" + item["date"]))

    def test_without_a_group_the_person_signs_as_always(self):
        u = self.user("gpb3")
        admin = self.admin()
        self.photo(u, "Pinna nobilis/b.png")
        res = u.submit_species("Pinna nobilis")
        admin.approve_submission(res["id"])
        item = [i for i in u.catalog("photos") if i["sent_by"] == "gpb3"][0]
        self.assertEqual((item["uploader"], item["group"]), ("gpb3", ""))

    def test_nobody_publishes_for_a_group_they_are_not_in(self):
        boss, _member = self.group("Closed2", "gpc")
        stranger = self.user("gpc3")
        self.photo(stranger, "Pinna nobilis/c.png")
        with self.assertRaises(ApiError) as e:
            stranger.submit_species("Pinna nobilis", "photos", "Closed2")
        self.assertEqual(e.exception.status, 403)

    def test_a_dataset_can_also_be_published_for_the_group(self):
        boss, member = self.group("Data", "gpd")
        admin = self.admin()
        yaml = self.tmp / "data.yaml"
        yaml.write_text("names: [crab]\n")
        member.upload("datasets", "set-group/data.yaml", yaml)
        image = self.tmp / "a.png"
        image.write_bytes(png_bytes())
        member.upload("datasets", "set-group/images/a.png", image)
        label = self.tmp / "a.txt"
        label.write_text("0 0.5 0.5 0.2 0.2\n")
        member.upload("datasets", "set-group/labels/a.txt", label)
        res = member.submit_dataset("set-group", "Data")
        self.assertEqual(res["group"], "Data")
        out = admin.approve_submission(res["id"])
        self.assertIn("_Data_", out["name"])


if __name__ == "__main__":
    unittest.main()
