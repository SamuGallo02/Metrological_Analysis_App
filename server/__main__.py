"""python -m server  serve | lan | status | doctor | backup | backups | restore | users | create-admin | hash-key"""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional

from common.errors import AppError
from common.params import ROLE_SERVER, ROLE_USER
from common.paths import LOCAL_DIR

from .app import make_server
from .config import hash_key, load_admin_key
from .db import Database
from .ops import backup as bk
from .ops import logsetup, network, stats
from .params import DEFAULT_PORT, RATE_LIMIT_PER_MIN

MIN_KEY_LEN = 16


def weak_key(key: str) -> bool:
    """A plain key shorter than MIN_KEY_LEN is guessable; a sha256: fingerprint is not judged (the key is unknown)."""
    return bool(key) and not key.lower().startswith("sha256:") and len(key) < MIN_KEY_LEN


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="server", description="Users and database server")
    ap.add_argument("--data", default=str(LOCAL_DIR), help="data folder (database and files); by default the local data folder of the app")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sv = sub.add_parser("serve", help="start the server")
    sv.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to accept connections from the network")
    sv.add_argument("--lan", action="store_true", help="shortcut for --host 0.0.0.0: reachable from other devices on the network")
    sv.add_argument("--public", action="store_true", help="reached from the Internet through a tunnel/proxy on this computer: "
                    "implies --trust-proxy and applies the same safety rules as --lan")
    sv.add_argument("--port", type=int, default=DEFAULT_PORT)
    sv.add_argument("--no-register", action="store_true", help="only administrators create accounts")
    sv.add_argument("--trust-proxy", action="store_true", help="behind Caddy/nginx: client IP from X-Forwarded-For")
    sv.add_argument("--rate-limit", type=int, default=RATE_LIMIT_PER_MIN, help="requests per minute per address (0 = unlimited)")
    sv.add_argument("--allow-weak-key", action="store_true", help="keep a short admin key even when the server is reachable from the network")

    sub.add_parser("lan", help="show the addresses other devices must use to reach this computer")
    st = sub.add_parser("status", help="users, sessions, disk and data sizes (works with the server stopped)")
    st.add_argument("--json", action="store_true")
    sub.add_parser("doctor", help="check configuration, database, disk and key before going online")

    b = sub.add_parser("backup", help="backup of the database (and, with --files, of all the data)")
    b.add_argument("--out", help="destination folder (default: <data>/backups)")
    b.add_argument("--files", action="store_true", help="also a .tar.gz of the whole data folder")
    b.add_argument("--keep", type=int, default=14, help="number of backups to keep")
    bl = sub.add_parser("backups", help="list the backups")
    bl.add_argument("--out")
    r = sub.add_parser("restore", help="restore the database from a backup (server stopped)")
    r.add_argument("file")

    u = sub.add_parser("users", help="list users or manage an account without the app")
    us = u.add_subparsers(dest="action", required=True)
    us.add_parser("list")
    for name in ("passwd", "disable", "enable", "unlock"):
        us.add_parser(name).add_argument("username")
    us.choices["passwd"].add_argument("--password", help="asked if omitted")

    ca = sub.add_parser("create-admin", help="create an administrator account")
    ca.add_argument("username")
    ca.add_argument("--password", help="asked if omitted")
    sub.add_parser("hash-key", help="print the sha256: form of an access key, to store instead of the plain key")
    return ap


def _db(data: Path) -> Database:
    return Database(data / "server.db")


def _find_user(db: Database, username: str) -> dict:
    for u in db.list_users():
        if u["username"].lower() == username.lower():
            return u
    raise bk.BackupError(f"User not found: {username}")


# ---- commands ----------------------------------------------------------------
def cmd_lan(port: int = DEFAULT_PORT) -> int:
    addrs = network.lan_addresses()
    if not addrs:
        print("No network address found: is this computer connected to a network?")
        return 1
    print("Other devices on the SAME network (Wi-Fi/LAN) can use:")
    for a in addrs:
        print(f"  http://{a}:{port}")
    a = addrs[0]
    print("\nOn the other device, start the app with the server address:")
    print(f"  Windows (cmd):   set AM_SERVER_URL=http://{a}:{port} && python main.py")
    print(f"  macOS / Linux:   AM_SERVER_URL=http://{a}:{port} python3 main.py")
    print("\nTest from a phone or browser:  http://%s:%d/api/health   (it must answer {\"ok\": true, ...})" % (a, port))
    print("If it does not answer: allow the port in the firewall (deploy/windows/open_firewall.cmd as administrator),")
    print("and check that the Wi-Fi does not isolate devices (guest networks often do).")
    print("Outside your network (temporary, with HTTPS): see deploy/README.md, section \"Temporary access from the Internet\".")
    return 0


def cmd_status(data: Path, as_json: bool) -> int:
    s = stats.collect(_db(data), data)
    if as_json:
        print(json.dumps(s, indent=2))
        return 0
    print(f"Data folder : {data.resolve()}")
    print(f"Users       : {s['users']} ({s['admins']} administrators), {s['sessions']} active sessions")
    print(f"Last 24 h   : {s['events_24h']} events, {s['logins_24h']} logins")
    print(f"Database    : {stats.human(s['db_bytes'])}")
    for area, size in s["areas"].items():
        print(f"  {area:<9} : {stats.human(size)}")
    print(f"Disk        : {stats.human(s['disk_free'])} free of {stats.human(s['disk_total'])}")
    return 0


def cmd_doctor(data: Path, port: int) -> int:
    problems = 0

    def line(ok: Optional[bool], text: str) -> None:
        nonlocal problems
        mark = {True: "[OK]  ", False: "[FAIL]", None: "[WARN]"}[ok]
        problems += ok is False
        print(f"{mark} {text}")

    line(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} (3.10+ required)")
    try:
        data.mkdir(parents=True, exist_ok=True)
        probe = data / ".write_test"
        probe.write_text("x")
        probe.unlink()
        line(True, f"Data folder writable: {data.resolve()}")
    except OSError as e:
        line(False, f"Data folder not writable: {e}")
        return 1
    db_file = data / "server.db"
    if db_file.exists():
        try:
            con = sqlite3.connect(str(db_file))
            res = con.execute("PRAGMA integrity_check").fetchone()[0]
            con.close()
            line(res == "ok", f"Database integrity: {res}")
        except sqlite3.DatabaseError as e:
            line(False, f"Database damaged: {e}")
    else:
        line(None, "Database not created yet (it is created on first start)")
    db = _db(data)
    line(db.count_admins() > 0 or None, f"Administrators: {db.count_admins()}" +
         ("" if db.count_admins() else "  -> python -m server create-admin NAME"))
    key = load_admin_key(data)
    if not key:
        line(True, "Admin access key disabled (admin accounts only through create-admin)")
    else:
        line(not weak_key(key) or None, "Admin access key: " + ("SHORT/guessable: not allowed when reachable from the network"
                                                                if weak_key(key) else "strong or stored as sha256"))
    free = shutil.disk_usage(data).free
    line(free > (2 << 30) or None, f"Free disk space: {stats.human(free)}")
    line(not network.port_in_use(port) or None, f"Port {port} " + ("is already in use (server already running?)"
                                                                  if network.port_in_use(port) else "is free"))
    addrs = network.lan_addresses()
    line(bool(addrs) or None, "Network addresses: " + (", ".join(addrs) if addrs else "none found"))
    backups = bk.list_backups(data / "backups")
    line(bool(backups) or None, f"Backups: {len(backups)}" + ("" if backups else "  -> python -m server backup"))
    print("\nEverything is fine." if not problems else f"\n{problems} problem(s) to fix.")
    return 1 if problems else 0


def cmd_backup(data: Path, out: Optional[str], files: bool, keep: int) -> int:
    dest = Path(out) if out else data / "backups"
    made = [bk.backup_db(data / "server.db", dest)]
    if files:
        made.append(bk.backup_files(data, dest))
    for p in made:
        print(f"Created {p}  ({stats.human(p.stat().st_size)})")
    for p in bk.prune(dest, keep):
        print(f"Removed old backup {p.name}")
    return 0


def cmd_users(data: Path, a) -> int:
    db = _db(data)
    if a.action == "list":
        for u in db.list_users():
            last = time.strftime("%Y-%m-%d %H:%M", time.localtime(u["last_login"])) if u["last_login"] else "never"
            print(f"{u['id']:>3}  {u['username']:<20} {u['role']:<7} {'active' if u['active'] else 'DISABLED':<9} last login: {last}")
        return 0
    u = _find_user(db, a.username)
    if a.action == "passwd":
        db.update_user(u["id"], password=a.password or getpass.getpass("New password: "))
        print(f"Password of '{u['username']}' changed (its sessions are closed).")
    elif a.action in ("disable", "enable"):
        db.update_user(u["id"], active=(a.action == "enable"))
        print(f"'{u['username']}' {'enabled' if a.action == 'enable' else 'disabled'}.")
    elif a.action == "unlock":
        with db._c() as c:
            c.execute("UPDATE users SET failed=0, locked_until=0 WHERE id=?", (u["id"],))
        print(f"'{u['username']}' unlocked.")
    return 0


def cmd_serve(data: Path, a) -> int:
    host = "0.0.0.0" if a.lan else a.host
    log_file = logsetup.setup(data)
    exposed = a.public or not network.is_loopback(host)          # a tunnel reaches 127.0.0.1 but is public all the same
    if _db(data).count_admins() == 0:
        print("NOTE: no administrator yet. Create one with:  python -m server create-admin NAME")
    key = load_admin_key(data)
    if exposed and weak_key(key) and not a.allow_weak_key:
        print(f"WARNING: the admin access key is shorter than {MIN_KEY_LEN} characters and the server is reachable from the network.")
        print("         The key is DISABLED for this run (admin accounts keep working). Use a longer key, or --allow-weak-key.")
        key = ""
    httpd = make_server(data, host, a.port, not a.no_register, key, a.trust_proxy or a.public, a.rate_limit)
    print(f"Listening on http://{host}:{a.port}  (data in {data.resolve()})")
    print(f"Log file: {log_file}")
    print("Admin access key: " + ("enabled" if key else "DISABLED (set AM_ADMIN_KEY or server/admin_key.txt)"))
    if a.public:
        print("Public mode: start the tunnel in another window, e.g.  cloudflared tunnel --url http://127.0.0.1:%d" % a.port)
    elif exposed:
        print("Reachable from other devices at:")
        for u in network.urls(a.port) or ["(no network address found)"]:
            print("  " + u)
        print("Put an HTTPS proxy (Caddy/nginx) in front for anything but a private test: passwords travel in clear.")
    print("Stop with Ctrl+C.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        httpd.server_close()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    a = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    data = Path(a.data)
    try:
        if a.cmd == "hash-key":
            print(hash_key(getpass.getpass("Access key: ")))
            return 0
        if a.cmd == "create-admin":
            u = _db(data).create_user(a.username, a.password or getpass.getpass("Password: "), ROLE_SERVER)
            print(f"Administrator '{u['username']}' created.")
            return 0
        if a.cmd == "lan":
            return cmd_lan()
        if a.cmd == "status":
            return cmd_status(data, a.json)
        if a.cmd == "doctor":
            return cmd_doctor(data, DEFAULT_PORT)
        if a.cmd == "backup":
            return cmd_backup(data, a.out, a.files, a.keep)
        if a.cmd == "backups":
            for p in bk.list_backups(Path(a.out) if a.out else data / "backups"):
                print(f"{p.name}  {stats.human(p.stat().st_size)}")
            return 0
        if a.cmd == "restore":
            saved = bk.restore_db(Path(a.file), data / "server.db", network.port_in_use(DEFAULT_PORT))
            print("Database restored." + (f" The previous one is saved as {saved.name}." if saved else ""))
            return 0
        if a.cmd == "users":
            return cmd_users(data, a)
        if a.cmd == "serve":
            return cmd_serve(data, a)
    except (AppError, bk.BackupError) as e:
        print("Error:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
