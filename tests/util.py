"""Test server and common test utilities."""
import struct, tempfile, threading, zlib
from pathlib import Path

from common.errors import AppError
from common.params import ROLE_SERVER
from server.app import make_server
from server.db import Database

KEY = "test-key-9f3"


def png_bytes():
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


class TestServer:
    """Starts a temporary server with an 'admin' administrator and the key KEY."""
    def __init__(self, **kw):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "srv"
        Database(self.data / "server.db").create_user("admin", "adminpass1", ROLE_SERVER)
        kw.setdefault("admin_key", KEY)
        self.httpd = make_server(self.data, "127.0.0.1", 0, **kw)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.tmp.cleanup()

def upload_as_user(store, rel, username="francy", area="species", data=b"x"):
    """Simula l'upload di un utente normale: il file finisce davvero in quarantena."""
    dest, eff = store.check_new_file(area, rel, False, username, 10)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest, eff

class FakeServerClient:
    """Finge il server: l'albero è un dizionario (cartella = dizionario, file = bytes)."""
    def __init__(self, tree):
        self.tree, self.downloaded = tree, []

    def _node(self, rel):
        node = self.tree
        for part in filter(None, rel.split("/")):
            node = node[part]
        return node

    def list(self, area, rel=""):
        return [{"name": n, "type": "dir" if isinstance(v, dict) else "file",
                 "size": 0 if isinstance(v, dict) else len(v)} for n, v in self._node(rel).items()]

    def download(self, area, rel, dest, progress=None, cancel=None):
        try:
            data = self._node(rel)
        except KeyError:
            raise AppError("File not found.", 404) from None
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        self.downloaded.append(rel)
        if progress:
            progress(len(data), len(data))
        return dest
    
def pump(cond, secs=8):
    """Fa girare Qt finché la condizione è vera (o scade il tempo): per le finestre che lavorano in background."""
    import time
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    t = time.time()
    while time.time() - t < secs and not cond():
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    return cond()