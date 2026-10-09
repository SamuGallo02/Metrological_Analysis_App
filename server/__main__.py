"""python -m server serve | create-admin | hash-key"""
from __future__ import annotations

import argparse
import getpass
import logging
import sys
from pathlib import Path

from common.errors import AppError
from common.params import ROLE_SERVER

from .app import make_server
from .config import hash_key, load_admin_key
from .db import Database
from .params import DEFAULT_PORT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="server", description="Users and database server")
    ap.add_argument("--data", default="server_data", help="data folder (users and files)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve", help="start the server")
    sv.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to accept connections from the network")
    sv.add_argument("--port", type=int, default=DEFAULT_PORT)
    sv.add_argument("--no-register", action="store_true", help="only administrators create accounts")
    sv.add_argument("--trust-proxy", action="store_true", help="behind Caddy/nginx: client IP from X-Forwarded-For")
    ca = sub.add_parser("create-admin", help="create an administrator account")
    ca.add_argument("username")
    ca.add_argument("--password", help="asked if omitted")
    sub.add_parser("hash-key", help="print the sha256: form of an access key, to store instead of the plain key")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    data = Path(a.data)

    if a.cmd == "hash-key":
        print(hash_key(getpass.getpass("Access key: ")))
        return 0
    if a.cmd == "create-admin":
        try:
            u = Database(data / "server.db").create_user(a.username, a.password or getpass.getpass("Password: "), ROLE_SERVER)
        except AppError as e:
            print("Error:", e)
            return 1
        print(f"Administrator '{u['username']}' created.")
        return 0

    if Database(data / "server.db").count_admins() == 0:
        print("NOTE: no administrator yet. Create one with:  python -m server create-admin NAME")
    key = load_admin_key(data)
    httpd = make_server(data, a.host, a.port, not a.no_register, key, a.trust_proxy)
    print(f"Listening on http://{a.host}:{a.port}  (data in {data.resolve()})")
    print("Admin access key: " + ("enabled" if key else "DISABLED (set AM_ADMIN_KEY or server/admin_key.txt)"))
    if key and not key.lower().startswith("sha256:") and len(key) < 12:
        print("WARNING: the access key is short/guessable: use a long random key before going online.")
    if a.host not in ("127.0.0.1", "localhost"):
        print("Put an HTTPS proxy (Caddy/nginx) in front: passwords must not travel in clear.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
