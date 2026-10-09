"""Test server and common test utilities."""
import struct, tempfile, threading, zlib
from pathlib import Path

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
