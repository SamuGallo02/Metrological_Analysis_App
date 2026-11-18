"""Store for users, sessions and activity log (SQLite).

Autore: Samuele Gallo
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.errors import AppError
from common.params import (GROUP_ADMIN, GROUP_MEMBER, GROUP_NAME_RE, GROUP_ROLES, JOB_CANCELLED, JOB_DONE,
                           JOB_FAILED, JOB_QUEUED, JOB_RUNNING, ROLE_SERVER, ROLE_USER, ROLES, VIS_GROUP,
                           VIS_PRIVATE, VIS_PUBLIC, VISIBILITIES)
from common.security import (hash_password, new_token, token_digest, validate_password, validate_username,
                             verify_password)

from .params import (DEFAULT_QUOTA_MB, DEFAULT_GROUP_QUOTA_MB, LOGIN_LOCK_SECONDS, LOGIN_MAX_FAILS, PROFILE_FIELDS,
                     SUBMISSION_APPROVED, SUBMISSION_PENDING, SUBMISSION_REJECTED, TOKEN_TTL, KIND_PHOTOS, KIND_DATASET, KIND_MODEL)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COLUMNS = {"full_name": "TEXT NOT NULL DEFAULT ''", "email": "TEXT NOT NULL DEFAULT ''",
            "organization": "TEXT NOT NULL DEFAULT ''", "phone": "TEXT NOT NULL DEFAULT ''",
            "bio": "TEXT NOT NULL DEFAULT ''", "quota_mb": "INTEGER NOT NULL DEFAULT 0",
            "pending": "INTEGER NOT NULL DEFAULT 0"}     # registered, waiting for an administrator's approval


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._c() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              role TEXT NOT NULL, salt TEXT NOT NULL, pw_hash TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL,
              last_login REAL, failed INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS tokens(
              digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, username TEXT NOT NULL,
              action TEXT NOT NULL, area TEXT, path TEXT, size INTEGER);
            CREATE TABLE IF NOT EXISTS submissions(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL, species TEXT NOT NULL, path TEXT NOT NULL,
              status TEXT NOT NULL, photos INTEGER NOT NULL DEFAULT 0,
              created REAL NOT NULL, reviewed_by TEXT, reviewed REAL,
              group_name TEXT NOT NULL DEFAULT '',
              visibility TEXT NOT NULL DEFAULT 'public',
              vis_group TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS training_jobs(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL, dataset TEXT NOT NULL, base_model TEXT NOT NULL,
              epochs INTEGER NOT NULL, imgsz INTEGER NOT NULL, batch INTEGER NOT NULL,
              species TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
              created REAL NOT NULL, started REAL, finished REAL,
              worker TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '',
              model TEXT NOT NULL DEFAULT '', metrics TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS enhance_jobs(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL, area TEXT NOT NULL, path TEXT NOT NULL,
              method TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
              created REAL NOT NULL, started REAL, finished REAL,
              worker TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '',
              result TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS groups(
              name TEXT PRIMARY KEY COLLATE NOCASE, created REAL NOT NULL, created_by TEXT NOT NULL DEFAULT '',
              description TEXT NOT NULL DEFAULT '', free_upload INTEGER NOT NULL DEFAULT 0,
              quota_mb INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS group_members(
              group_name TEXT NOT NULL COLLATE NOCASE, username TEXT NOT NULL COLLATE NOCASE,
              added REAL NOT NULL, role TEXT NOT NULL DEFAULT 'member', PRIMARY KEY(group_name, username));
            DROP INDEX IF EXISTS one_pending_per_folder;
            """)
            have = {r[1] for r in c.execute("PRAGMA table_info(users)")}
            for col, decl in _COLUMNS.items():
                if col not in have:                          # database created by a previous version
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
            have = {r[1] for r in c.execute("PRAGMA table_info(submissions)")}
            if "kind" not in have:                           # database created by a previous version
                c.execute(f"ALTER TABLE submissions ADD COLUMN kind TEXT NOT NULL DEFAULT '{KIND_PHOTOS}'")
            if "visibility" not in have:                     # before the groups: everything was seen by everyone
                c.execute(f"ALTER TABLE submissions ADD COLUMN visibility TEXT NOT NULL DEFAULT '{VIS_PUBLIC}'")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_pending_per_item "       # photos and stereo of a species can both wait
                      "ON submissions(kind, path) WHERE status='pending'")
            self._add_missing_columns(c)

    @staticmethod
    def _add_missing_columns(c) -> None:
        """Columns added to tables that a server has been using since before: CREATE TABLE IF NOT EXISTS leaves an
        existing table as it is, so they are added here (an empty database already has them and nothing happens)."""
        later = {"groups": (("description", "TEXT NOT NULL DEFAULT ''"),
                            ("free_upload", "INTEGER NOT NULL DEFAULT 0"),
                            ("quota_mb", "INTEGER NOT NULL DEFAULT 0")),
                 "group_members": (("role", f"TEXT NOT NULL DEFAULT '{GROUP_MEMBER}'"),),
                 "submissions": (("group_name", "TEXT NOT NULL DEFAULT ''"),)}
        added = False
        for table, columns in later.items():
            have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            for name, decl in columns:
                if name not in have:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                    added = True
        if added:        # groups made before the roles existed: whoever made one looks after it
            c.execute("INSERT OR IGNORE INTO group_members(group_name, username, role, added)"
                      " SELECT name, created_by, ?, created FROM groups WHERE created_by<>''", (GROUP_ADMIN,))
            c.execute("UPDATE group_members SET role=? WHERE username="
                      "(SELECT created_by FROM groups WHERE name=group_name)", (GROUP_ADMIN,))

    def _c(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path), timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return _Ctx(con)

    # ---- users ------------------------------------------------------------
    def create_user(self, username: str, password: str, role: str = ROLE_USER, email: str = "",
                    pending: bool = False) -> Dict[str, Any]:
        """pending=True: the account cannot sign in until an administrator enables it."""
        username, password = validate_username(username), validate_password(password)
        email = email.strip() if isinstance(email, str) else ""
        if email and (len(email) > PROFILE_FIELDS["email"] or not _EMAIL.match(email)):
            raise AppError("Invalid email address.")
        if role not in ROLES:
            raise AppError("Invalid role.")
        salt, h = hash_password(password)
        try:
            with self._c() as c:
                uid = c.execute("INSERT INTO users(username,role,salt,pw_hash,created,email,active,pending) "
                                "VALUES(?,?,?,?,?,?,?,?)", (username, role, salt, h, time.time(), email,
                                                            0 if pending else 1, 1 if pending else 0)).lastrowid
        except sqlite3.IntegrityError:
            raise AppError("Username already taken.", 409)
        return self.get_user(uid)

    def get_user(self, uid: int) -> Optional[Dict[str, Any]]:
        with self._c() as c:
            r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return _public(r) if r else None

    def list_users(self) -> List[Dict[str, Any]]:
        with self._c() as c:
            return [_public(r) for r in c.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE")]

    def count_admins(self) -> int:
        with self._c() as c:
            return c.execute("SELECT COUNT(*) FROM users WHERE role=? AND active=1", (ROLE_SERVER,)).fetchone()[0]

    def update_user(self, uid: int, role: Optional[str] = None, active: Optional[bool] = None,
                    password: Optional[str] = None, quota_mb: Optional[int] = None) -> Dict[str, Any]:
        u = self.get_user(uid)
        if not u:
            raise AppError("User not found.", 404)
        demoting = u["role"] == ROLE_SERVER and u["active"] and (
            (role is not None and role != ROLE_SERVER) or (active is not None and not active))
        if demoting and self.count_admins() <= 1:
            raise AppError("At least one active administrator must remain.")
        with self._c() as c:
            if role is not None:
                if role not in ROLES:
                    raise AppError("Invalid role.")
                c.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
            if active is not None:
                c.execute("UPDATE users SET active=?, pending=0 WHERE id=?", (1 if active else 0, uid))   # enabling approves
                if not active:
                    c.execute("DELETE FROM tokens WHERE user_id=?", (uid,))
            if quota_mb is not None:
                if not isinstance(quota_mb, int) or isinstance(quota_mb, bool) or not 0 <= quota_mb <= 1 << 20:
                    raise AppError("Invalid quota.")
                c.execute("UPDATE users SET quota_mb=? WHERE id=?", (quota_mb, uid))
            if password is not None:
                salt, h = hash_password(validate_password(password))
                c.execute("UPDATE users SET salt=?,pw_hash=?,failed=0,locked_until=0 WHERE id=?", (salt, h, uid))
                c.execute("DELETE FROM tokens WHERE user_id=?", (uid,))
        return self.get_user(uid)

    def promote(self, uid: int) -> Dict[str, Any]:
        """Makes the account a permanent administrator (correct access key)."""
        return self.update_user(uid, role=ROLE_SERVER)

    def update_profile(self, uid: int, data: Dict[str, Any]) -> Dict[str, Any]:
        values: Dict[str, str] = {}
        for field, limit in PROFILE_FIELDS.items():
            if field not in data:
                continue
            v = data[field]
            if not isinstance(v, str):
                raise AppError("Invalid value for {field}.", field=field)
            v = v.strip()
            if len(v) > limit:
                raise AppError("{field} is too long (max {n} characters).", field=field, n=limit)
            if field == "email" and v and not _EMAIL.match(v):
                raise AppError("Invalid email address.")
            values[field] = v
        if values:
            with self._c() as c:
                c.execute("UPDATE users SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?",
                          (*values.values(), uid))
        return self.get_user(uid)

    def delete_user(self, uid: int) -> None:
        u = self.get_user(uid)
        if not u:
            raise AppError("User not found.", 404)
        if u["role"] == ROLE_SERVER and u["active"] and self.count_admins() <= 1:
            raise AppError("At least one active administrator must remain.")
        with self._c() as c:
            c.execute("DELETE FROM users WHERE id=?", (uid,))

    # ---- login -----------------------------------------------------------
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """Verifies credentials (5 wrong passwords -> account locked for 5 minutes). Does not issue tokens."""
        with self._c() as c:
            r = c.execute("SELECT * FROM users WHERE username=?", ((username or "").strip(),)).fetchone()
            if r is None:
                hash_password(password or "")          # similar response time if the user does not exist
                raise AppError("Invalid credentials.", 401)
            now = time.time()
            if r["locked_until"] > now:
                left = r["locked_until"] - now
                raise AppError("Too many attempts: try again in {minutes} min.", 429,
                               minutes=max(1, int((left + 59) // 60)), scope="account", retry_after=int(left) + 1)
            if not r["active"]:
                if r["pending"] and verify_password(password or "", r["salt"], r["pw_hash"]):
                    raise AppError("Your account is waiting for approval by an administrator.", 403)
                raise AppError("Account disabled.", 403)
            if not verify_password(password or "", r["salt"], r["pw_hash"]):
                fails = r["failed"] + 1
                lock = now + LOGIN_LOCK_SECONDS if fails >= LOGIN_MAX_FAILS else 0
                c.execute("UPDATE users SET failed=?, locked_until=? WHERE id=?", (0 if lock else fails, lock, r["id"]))
                c.commit()
                raise AppError("Invalid credentials.", 401)
            c.execute("UPDATE users SET failed=0, locked_until=0, last_login=? WHERE id=?", (now, r["id"]))
        return self.get_user(r["id"])

    def issue_token(self, uid: int) -> str:
        token, now = new_token(), time.time()
        with self._c() as c:
            c.execute("DELETE FROM tokens WHERE expires<?", (now,))
            c.execute("INSERT INTO tokens(digest,user_id,expires) VALUES(?,?,?)",
                      (token_digest(token), uid, now + TOKEN_TTL))
        return token

    def user_from_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self._c() as c:
            r = c.execute("""SELECT u.* FROM tokens t JOIN users u ON u.id=t.user_id
                             WHERE t.digest=? AND t.expires>? AND u.active=1""",
                          (token_digest(token), time.time())).fetchone()
        return _public(r) if r else None

    def logout(self, token: str) -> None:
        with self._c() as c:
            c.execute("DELETE FROM tokens WHERE digest=?", (token_digest(token),))

    # ---- activity log ------------------------------------------------
    def log(self, username: str, action: str, area: str = "", path: str = "", size: int = 0) -> None:
        with self._c() as c:
            c.execute("INSERT INTO events(ts,username,action,area,path,size) VALUES(?,?,?,?,?,?)",
                      (time.time(), username, action, area, path, size))

    def events(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._c() as c:
            return [dict(r) for r in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]
        
    # ---- submissions: folders uploaded by users, waiting for review --------
    def add_submission(self, username: str, species: str, path: str, photos: int = 0,
                       kind: str = KIND_PHOTOS, group: str = "", visibility: str = VIS_PUBLIC,
                       vis_group: str = "") -> int:
        """`group`: published on behalf of a work group the user belongs to (the group is then the author).
        `visibility` + `vis_group`: who may see it once approved (everybody, one group, or the uploader)."""
        visibility, vis_group = check_visibility(visibility, vis_group or group)
        try:
            with self._c() as c:
                return c.execute("INSERT INTO submissions(username,species,path,status,photos,created,kind,"
                                 "group_name,visibility,vis_group) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                 (username, species, path, SUBMISSION_PENDING, photos, time.time(),
                                  kind, group, visibility, vis_group)).lastrowid
        except sqlite3.IntegrityError:
            raise AppError("You already have a pending submission for this species.", 409) from None

    def list_submissions(self, username: Optional[str] = None, status: Optional[str] = None,
                         kind: Optional[str] = None, groups: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """username: only that user's rows; with `groups`, also the rows shared with those work groups
        (never the private ones, which stay with whoever sent them)."""
        where, args = [], []
        if username is not None and groups:
            marks = ",".join("?" * len(groups))
            where.append(f"(username=? OR (vis_group IN ({marks}) COLLATE NOCASE AND visibility!=?))")
            args += [username, *groups, VIS_PRIVATE]
        elif username is not None:
            where.append("username=?")
            args.append(username)
        if status is not None:
            where.append("status=?")
            args.append(status)
        if kind is not None:
            where.append("kind=?")
            args.append(kind)
        query = "SELECT * FROM submissions"        
        if where:
            query += " WHERE " + " AND ".join(where)
        with self._c() as c:
            return [dict(r) for r in c.execute(query + " ORDER BY id DESC", args)]
        
    def set_submission_kind(self, old_kind: str, path: str, new_kind: str, status: Optional[str] = None) -> int:
        """Changes the kind of the rows of an item (used when the layout is reorganised). Returns how many rows."""
        with self._c() as c:
            query, args = "UPDATE submissions SET kind=? WHERE kind=? AND path=?", [new_kind, old_kind, path]
            if status:
                query, args = query + " AND status=?", args + [status]
            return c.execute(query, args).rowcount

    def restricted_submissions(self) -> List[Dict[str, Any]]:
        """The approved items NOT visible to everyone (to hide them from the users who may not see them)."""
        with self._c() as c:
            return [dict(r) for r in c.execute(
                "SELECT id, kind, path, username, visibility, vis_group FROM submissions "
                "WHERE status=? AND visibility!=?",
                (SUBMISSION_APPROVED, VIS_PUBLIC))]

    def set_submission_visibility(self, sid: int, visibility: str, vis_group: str = "") -> Dict[str, Any]:
        """Who may see an item: everyone, one work group, or only whoever sent it."""
        visibility, vis_group = check_visibility(visibility, vis_group)
        with self._c() as c:
            if c.execute("UPDATE submissions SET visibility=?, vis_group=? WHERE id=?",
                         (visibility, vis_group, sid)).rowcount == 0:
                raise AppError("Submission not found.", 404)
        return self.get_submission(sid)

    def user_by_name(self, username: str) -> Optional[Dict[str, Any]]:
        with self._c() as c:
            r = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return _public(r) if r else None

    def get_submission(self, sid: int) -> Dict[str, Any]:
        with self._c() as c:
            row = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise AppError("Submission not found.", 404)
        return dict(row)
    
    def review_submission(self, sid: int, status: str, reviewer: str,
                          path: Optional[str] = None, photos: Optional[int] = None) -> Dict[str, Any]:
        if status not in (SUBMISSION_APPROVED, SUBMISSION_REJECTED):
            raise AppError("Invalid review status.")
        with self._c() as c:
            row = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
            if row is None:
                raise AppError("Submission not found.", 404)
            if row["status"] != SUBMISSION_PENDING:
                raise AppError("This submission has already been reviewed.", 409)
            c.execute("UPDATE submissions SET status=?, reviewed_by=?, reviewed=?, "
                      "path=COALESCE(?, path), photos=COALESCE(?, photos) WHERE id=?",
                      (status, reviewer, time.time(), path, photos, sid))
            return dict(c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone())

    # ---- work groups ------------------------------------------------------
    def create_group(self, name: str, created_by: str = "") -> Dict[str, Any]:
        """A group shares a folder on the server. Anybody can make one: whoever makes it is its first administrator,
        and the name is used as a folder name, so it is kept simple."""
        name = (name or "").strip()
        if not re.fullmatch(GROUP_NAME_RE, name):
            raise AppError("The name of a group has 2 to 40 characters: letters, digits, spaces, - and _.", 422)
        with self._c() as c:
            if c.execute("SELECT 1 FROM groups WHERE name=?", (name,)).fetchone():
                raise AppError("A group with this name already exists.", 409)
            c.execute("INSERT INTO groups(name, created, created_by) VALUES(?,?,?)", (name, time.time(), created_by))
            if created_by:
                c.execute("INSERT INTO group_members(group_name, username, role, added) VALUES(?,?,?,?)",
                          (name, created_by, GROUP_ADMIN, time.time()))
        return self.group(name)

    def update_group(self, name: str, description: Optional[str] = None,
                     free_upload: Optional[bool] = None) -> Dict[str, Any]:
        """The settings of a group: what it is for, and whether the members may add files without waiting."""
        sets, args = [], []
        if description is not None:
            sets.append("description=?")
            args.append(description.strip()[:500])
        if free_upload is not None:
            sets.append("free_upload=?")
            args.append(1 if free_upload else 0)
        if sets:
            args.append(name)
            with self._c() as c:
                if not c.execute(f"UPDATE groups SET {', '.join(sets)} WHERE name=?", args).rowcount:
                    raise AppError("Group not found.", 404)
        return self.group(name)

    def set_group_quota(self, name: str, quota_mb: Any) -> Dict[str, Any]:
        """How much room the folder of the group has (0: no limit). Only a server administrator decides it."""
        try:
            quota = max(0, int(quota_mb or 0))
        except (TypeError, ValueError):
            raise AppError("Invalid quota.", 422) from None
        with self._c() as c:
            if not c.execute("UPDATE groups SET quota_mb=? WHERE name=?", (quota, name)).rowcount:
                raise AppError("Group not found.", 404)
        return self.group(name)

    def group_quota(self, name: str) -> int:
        with self._c() as c:
            row = c.execute("SELECT quota_mb FROM groups WHERE name=?", (name,)).fetchone()
        return int(row[0]) if row and row[0] else DEFAULT_GROUP_QUOTA_MB

    def group_free_upload(self, name: str) -> bool:
        with self._c() as c:
            row = c.execute("SELECT free_upload FROM groups WHERE name=?", (name,)).fetchone()
        return bool(row and row[0])

    def delete_group(self, name: str) -> None:
        """Deletes a group. What was shared only with it stays with whoever sent it (never becomes public)."""
        with self._c() as c:
            if not c.execute("DELETE FROM groups WHERE name=?", (name,)).rowcount:
                raise AppError("Group not found.", 404)
            c.execute("DELETE FROM group_members WHERE group_name=?", (name,))
            c.execute("UPDATE submissions SET visibility=? WHERE vis_group=? COLLATE NOCASE AND visibility=?",
                      (VIS_PRIVATE, name, VIS_GROUP))
            c.execute("UPDATE submissions SET vis_group='' WHERE vis_group=? COLLATE NOCASE", (name,))

    def _group_exists(self, c, group: str) -> None:
        if not c.execute("SELECT 1 FROM groups WHERE name=?", (group,)).fetchone():
            raise AppError("Group not found.", 404)

    def set_member(self, group: str, username: str, member: bool = True,
                   role: str = GROUP_MEMBER) -> List[Dict[str, str]]:
        """Adds or removes a member; returns the members afterwards. The last administrator cannot be removed,
        otherwise nobody could look after the group any more."""
        if role not in GROUP_ROLES:
            raise AppError("Unknown role in the group.", 422)
        with self._c() as c:
            self._group_exists(c, group)
            if member:
                if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                    raise AppError("User not found.", 404)
                c.execute("INSERT OR IGNORE INTO group_members(group_name, username, role, added) VALUES(?,?,?,?)",
                          (group, username, role, time.time()))
            else:
                self._keep_an_admin(c, group, username)
                c.execute("DELETE FROM group_members WHERE group_name=? AND username=?", (group, username))
        return self.group_members(group)

    def set_group_role(self, group: str, username: str, role: str) -> List[Dict[str, str]]:
        """Promotes a member to administrator of the group, or puts them back to member."""
        if role not in GROUP_ROLES:
            raise AppError("Unknown role in the group.", 422)
        with self._c() as c:
            self._group_exists(c, group)
            if role != GROUP_ADMIN:
                self._keep_an_admin(c, group, username)
            if not c.execute("UPDATE group_members SET role=? WHERE group_name=? AND username=?",
                             (role, group, username)).rowcount:
                raise AppError("This user is not a member of the group.", 404)
        return self.group_members(group)

    @staticmethod
    def _keep_an_admin(c, group: str, username: str) -> None:
        row = c.execute("SELECT role FROM group_members WHERE group_name=? AND username=?",
                        (group, username)).fetchone()
        if row is None or row[0] != GROUP_ADMIN:
            return
        others = c.execute("SELECT COUNT(*) FROM group_members WHERE group_name=? AND role=? AND username<>?",
                           (group, GROUP_ADMIN, username)).fetchone()[0]
        if not others:
            raise AppError("A group always needs one administrator: choose another one first.", 409)

    def group_members(self, group: str) -> List[Dict[str, str]]:
        with self._c() as c:
            rows = c.execute("SELECT username, role, added FROM group_members WHERE group_name=?"
                             " ORDER BY role, username", (group,))
            return [{"username": r[0], "role": r[1], "added": r[2]} for r in rows]

    def group_role(self, group: str, username: str) -> str:
        """The role of a user in a group: administrator, member, or nothing if they do not belong to it."""
        with self._c() as c:
            row = c.execute("SELECT role FROM group_members WHERE group_name=? AND username=?",
                            (group, username)).fetchone()
        return row[0] if row else ""

    def is_group_admin(self, group: str, username: str) -> bool:
        return self.group_role(group, username) == GROUP_ADMIN

    def user_groups(self, username: str) -> List[str]:
        """The groups a user belongs to (the folders they may open)."""
        with self._c() as c:
            return [r[0] for r in c.execute("SELECT group_name FROM group_members WHERE username=? ORDER BY group_name",
                                            (username,))]

    def admin_groups(self, username: str) -> List[str]:
        """The groups a user looks after (where they approve what the others send)."""
        with self._c() as c:
            return [r[0] for r in c.execute("SELECT group_name FROM group_members WHERE username=? AND role=?"
                                            " ORDER BY group_name", (username, GROUP_ADMIN))]

    def group(self, name: str) -> Dict[str, Any]:
        with self._c() as c:
            row = c.execute("SELECT name, created, created_by, description, free_upload, quota_mb "
                            "FROM groups WHERE name=?", (name,)).fetchone()
        if row is None:
            raise AppError("Group not found.", 404)
        return {"name": row[0], "created": row[1], "created_by": row[2], "description": row[3],
                "free_upload": bool(row[4]), "quota_mb": row[5] or DEFAULT_GROUP_QUOTA_MB,
                "members": self.group_members(row[0])}

    def list_groups(self, username: str = "", every: bool = False) -> List[Dict[str, Any]]:
        """With `every` (server administrators) all the groups, otherwise only the user's own. Every group carries
        its members and the role the user has in it."""
        with self._c() as c:
            names = [r[0] for r in c.execute("SELECT name, created_by FROM groups ORDER BY name")]
        out = []
        for n in names:
            role = self.group_role(n, username) if username else ""
            if every or role:
                out.append(dict(self.group(n), role=role, mine=bool(role)))
        return out

    # ---- training asked of the server -------------------------------------
    def add_training_job(self, username: str, dataset: str, base_model: str, epochs: int, imgsz: int, batch: int,
                         species: str = "") -> Dict[str, Any]:
        """Puts a training in the queue. The work is done by a worker with a GPU, not by the server."""
        with self._c() as c:
            cur = c.execute("INSERT INTO training_jobs(username, dataset, base_model, epochs, imgsz, batch, species,"
                            " status, created) VALUES(?,?,?,?,?,?,?,?,?)",
                            (username, dataset, base_model, epochs, imgsz, batch, species, JOB_QUEUED, time.time()))
            job_id = cur.lastrowid
        return self.training_job(job_id)

    def training_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        with self._c() as c:
            row = c.execute("SELECT * FROM training_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def training_jobs(self, username: str = "", status: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        """The jobs of a user (empty username: everybody's), newest first."""
        where, args = [], []
        if username:
            where.append("username=?")
            args.append(username)
        if status:
            where.append("status=?")
            args.append(status)
        sql = "SELECT * FROM training_jobs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def claim_training_job(self, worker: str) -> Optional[Dict[str, Any]]:
        """Gives the oldest waiting job to a worker, one at a time (nobody else can take the same one)."""
        with self._c() as c:
            row = c.execute("SELECT id FROM training_jobs WHERE status=? ORDER BY id LIMIT 1", (JOB_QUEUED,)).fetchone()
            if row is None:
                return None
            taken = c.execute("UPDATE training_jobs SET status=?, worker=?, started=? WHERE id=? AND status=?",
                              (JOB_RUNNING, worker, time.time(), row[0], JOB_QUEUED)).rowcount
        return self.training_job(row[0]) if taken else None

    def update_training_job(self, job_id: int, *, status: Optional[str] = None, message: Optional[str] = None,
                            model: Optional[str] = None, metrics: Optional[str] = None) -> Dict[str, Any]:
        sets, args = [], []
        for name, value in (("status", status), ("message", message), ("model", model), ("metrics", metrics)):
            if value is not None:
                sets.append(f"{name}=?")
                args.append(value)
        if status in (JOB_DONE, JOB_FAILED, JOB_CANCELLED):
            sets.append("finished=?")
            args.append(time.time())
        if not sets:
            return self.training_job(job_id) or {}
        args.append(job_id)
        with self._c() as c:
            if not c.execute(f"UPDATE training_jobs SET {', '.join(sets)} WHERE id=?", args).rowcount:
                raise AppError("Training request not found.", 404)
        return self.training_job(job_id) or {}

    def cancel_training_job(self, job_id: int, username: str, admin: bool) -> Dict[str, Any]:
        """Only the one who asked for it (or an administrator) cancels it, and only while it is still waiting."""
        job = self.training_job(job_id)
        if job is None:
            raise AppError("Training request not found.", 404)
        if not admin and job["username"] != username:
            raise AppError("This training was asked for by somebody else.", 403)
        if job["status"] != JOB_QUEUED:
            raise AppError("Only a training that is still waiting can be cancelled.", 409)
        return self.update_training_job(job_id, status=JOB_CANCELLED, message="")

    # ---- improvement of a photo or a video asked of the server ------------
    def add_enhance_job(self, username: str, area: str, path: str, method: str = "") -> Dict[str, Any]:
        """Puts an improvement in the queue. As for the training, a worker does the work, not the server."""
        with self._c() as c:
            cur = c.execute("INSERT INTO enhance_jobs(username, area, path, method, status, created)"
                            " VALUES(?,?,?,?,?,?)", (username, area, path, method, JOB_QUEUED, time.time()))
            job_id = cur.lastrowid
        return self.enhance_job(job_id)

    def enhance_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        with self._c() as c:
            row = c.execute("SELECT * FROM enhance_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def enhance_jobs(self, username: str = "", status: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        """The improvements asked for by a user (empty username: everybody's), newest first."""
        where, args = [], []
        if username:
            where.append("username=?")
            args.append(username)
        if status:
            where.append("status=?")
            args.append(status)
        sql = "SELECT * FROM enhance_jobs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def claim_enhance_job(self, worker: str) -> Optional[Dict[str, Any]]:
        """Gives the oldest waiting improvement to a worker, one at a time."""
        with self._c() as c:
            row = c.execute("SELECT id FROM enhance_jobs WHERE status=? ORDER BY id LIMIT 1", (JOB_QUEUED,)).fetchone()
            if row is None:
                return None
            taken = c.execute("UPDATE enhance_jobs SET status=?, worker=?, started=? WHERE id=? AND status=?",
                              (JOB_RUNNING, worker, time.time(), row[0], JOB_QUEUED)).rowcount
        return self.enhance_job(row[0]) if taken else None

    def update_enhance_job(self, job_id: int, *, status: Optional[str] = None, message: Optional[str] = None,
                           result: Optional[str] = None) -> Dict[str, Any]:
        sets, args = [], []
        for name, value in (("status", status), ("message", message), ("result", result)):
            if value is not None:
                sets.append(f"{name}=?")
                args.append(value)
        if status in (JOB_DONE, JOB_FAILED, JOB_CANCELLED):
            sets.append("finished=?")
            args.append(time.time())
        if not sets:
            return self.enhance_job(job_id) or {}
        args.append(job_id)
        with self._c() as c:
            if not c.execute(f"UPDATE enhance_jobs SET {', '.join(sets)} WHERE id=?", args).rowcount:
                raise AppError("Improvement request not found.", 404)
        return self.enhance_job(job_id) or {}

    def cancel_enhance_job(self, job_id: int, username: str, admin: bool) -> Dict[str, Any]:
        """Only the one who asked for it (or an administrator), and only while it is still waiting."""
        job = self.enhance_job(job_id)
        if job is None:
            raise AppError("Improvement request not found.", 404)
        if not admin and job["username"] != username:
            raise AppError("This improvement was asked for by somebody else.", 403)
        if job["status"] != JOB_QUEUED:
            raise AppError("Only an improvement that is still waiting can be cancelled.", 409)
        return self.update_enhance_job(job_id, status=JOB_CANCELLED, message="")


class _Ctx:
    """Connection that commits on exit and always closes."""
    def __init__(self, con):
        self.con = con

    def __enter__(self):
        return self.con

    def __exit__(self, et, ev, tb):
        try:
            if et is None:
                self.con.commit()
        finally:
            self.con.close()
        return False


def _public(r: sqlite3.Row) -> Dict[str, Any]:
    out = {"id": r["id"], "username": r["username"], "role": r["role"], "active": bool(r["active"]),
           "created": r["created"], "last_login": r["last_login"],
           "quota_mb": r["quota_mb"] or DEFAULT_QUOTA_MB, "pending": bool(r["pending"])}
    out.update({f: r[f] for f in PROFILE_FIELDS})
    return out


def check_visibility(visibility: Any, group: Any) -> tuple:
    """(visibility, group name) checked: a group is required for VIS_GROUP, and is kept otherwise only if given.
    Whether the user belongs to that group is checked by the caller."""
    visibility = visibility or VIS_PUBLIC
    if visibility not in VISIBILITIES:
        raise AppError("Invalid visibility.", 422)
    group = str(group or "").strip()
    if group and not re.fullmatch(GROUP_NAME_RE, group):
        raise AppError("Group not found.", 404)
    if visibility == VIS_GROUP and not group:
        raise AppError("Choose the group that can see it.", 422)
    return visibility, group
