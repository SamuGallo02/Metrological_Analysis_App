"""Without an account there is no token: the views must say so instead of letting the server answer 401.

And the check of the environment at startup must not read 25.000 files every time the application opens.
"""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from common.ambient.installer import integrity
from common.ui.server_state import server_note, server_ready


def session(online=True, client=object(), guest=False):
    return SimpleNamespace(online=online, client=client, is_guest=guest)


class ServerReadyTest(unittest.TestCase):
    def test_only_a_connected_account_can_use_the_server(self):
        self.assertTrue(server_ready(session()))
        self.assertFalse(server_ready(session(online=False)))
        self.assertFalse(server_ready(session(client=None)))
        self.assertFalse(server_ready(session(guest=True)))      # entered without an account: no token

    def test_the_note_tells_which_of_the_two_it_is(self):
        self.assertNotEqual(server_note(session(guest=True)), server_note(session(online=False)))
        self.assertTrue(server_note(session(guest=True)))
        self.assertTrue(server_note(session(online=False)))


class StartupScanTest(unittest.TestCase):
    def venv(self, tmp):
        sp = Path(tmp) / "Lib" / "site-packages"
        (sp / "thing-1.0.dist-info").mkdir(parents=True)
        (sp / "thing-1.0.dist-info" / "RECORD").write_text("thing/__init__.py,sha256=x,0\n", encoding="utf-8")
        return Path(tmp)

    def test_the_full_scan_is_skipped_until_something_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = self.venv(tmp)
            self.assertTrue(integrity.check_due(venv))           # never done
            integrity.mark_checked(venv)
            self.assertFalse(integrity.check_due(venv))          # same packages, just checked
            record = venv / "Lib" / "site-packages" / "thing-1.0.dist-info" / "RECORD"
            record.write_text("thing/__init__.py,sha256=x,1\n", encoding="utf-8")
            self.assertTrue(integrity.check_due(venv))           # a package changed: scan again

    def test_a_new_package_brings_the_scan_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = self.venv(tmp)
            integrity.mark_checked(venv)
            info = venv / "Lib" / "site-packages" / "other-2.0.dist-info"
            info.mkdir()
            (info / "RECORD").write_text("other/__init__.py,sha256=y,0\n", encoding="utf-8")
            self.assertTrue(integrity.check_due(venv))

    def test_after_a_fortnight_it_runs_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = self.venv(tmp)
            integrity.mark_checked(venv)
            stamp = venv / ".integrity.json"
            data = json.loads(stamp.read_text(encoding="utf-8"))
            data["checked"] = time.time() - 15 * 24 * 3600
            stamp.write_text(json.dumps(data), encoding="utf-8")
            self.assertTrue(integrity.check_due(venv))

    def test_a_damaged_stamp_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            venv = self.venv(tmp)
            (venv / ".integrity.json").write_text("{not json", encoding="utf-8")
            self.assertTrue(integrity.check_due(venv))


if __name__ == "__main__":
    unittest.main()
