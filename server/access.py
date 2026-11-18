"""Who sees what: library visibility (everyone / uploader and a work group / uploader only) and group folders.

An approved item of the library is a folder (photos, stereo, videos, datasets) or a model file with its .json; its
submission row says who may see it. Files with no submission (published before the visibility existed, or by an
administrator through the file API) are visible to everyone. Administrators see everything.

Autore: Magform
Autore: Samuele Gallo
"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from common.errors import AppError
from common.params import AREA_GROUPS, KIND_AREA, KIND_MODEL, VIS_PUBLIC, VIS_GROUP

from .params import PENDING
from .storage import clean_rel


class Access:
    def __init__(self, db, user: Dict[str, Any], admin: bool):
        self.db, self.user, self.admin = db, user, admin
        self.name = user["username"]
        self.groups: List[str] = list(db.user_groups(self.name))     # the work groups this user belongs to
        self.group_folders = {g.lower() for g in self.groups}
        self._hidden: Optional[Dict[str, List[str]]] = None

    # ---- submissions ----------------------------------------------------------
    def can_see(self, sub: Dict[str, Any]) -> bool:
        if self.admin or sub.get("username") == self.name:
            return True
        vis = sub.get("visibility") or VIS_PUBLIC
        if vis == VIS_PUBLIC:
            return True
        return vis == VIS_GROUP and str(sub.get("vis_group") or "").lower() in self.group_folders

    def check_group(self, group: str) -> None:
        """The user may share with this work group (a member of it; a server administrator with any group)."""
        if not group:
            return
        if group.lower() not in self.group_folders and not self.admin:
            raise AppError("Group not found.", 404)
        if self.admin:
            self.db.group(group)                                 # 404 if it does not exist

    # ---- library paths ---------------------------------------------------------
    def _hidden_paths(self) -> Dict[str, List[str]]:
        """{area: [paths of the approved items this user may not see]}"""
        if self._hidden is None:
            self._hidden = {}
            if not self.admin:
                for sub in self.db.restricted_submissions():
                    if not self.can_see(sub):
                        self._hidden.setdefault(KIND_AREA.get(sub["kind"], ""), []).append(sub)
        return self._hidden

    def visible(self, area: str, rel: str) -> bool:
        rel = clean_rel(rel)                                   # "a//b", "a/./b", "a\\b" are the same file as "a/b"
        for sub in self._hidden_paths().get(area, []):
            p = sub["path"]
            if rel == p or rel.startswith(p + "/"):
                return False
            if sub["kind"] == KIND_MODEL and rel == str(PurePosixPath(p).with_suffix(".json")):
                return False                                   # the model's metadata follows the model
        return True

    def contains_hidden(self, area: str, rel: str) -> bool:
        return bool(self.hidden_under(area, rel))

    def hidden_under(self, area: str, rel: str) -> List[str]:
        """Paths (relative to the area) of the hidden items inside the folder rel ("" = the whole area): what a job
        that walks the folder must skip."""
        rel = clean_rel(rel)
        out = []
        for sub in self._hidden_paths().get(area, []):
            p = sub["path"]
            if not rel or p.startswith(rel + "/"):
                out.append(p)
                if sub["kind"] == KIND_MODEL:
                    out.append(str(PurePosixPath(p).with_suffix(".json")))
        return out

    def check_file(self, area: str, rel: str) -> None:
        """404 (not 403: nothing is revealed) for what the user may not see."""
        if area == AREA_GROUPS:
            self.group_of(rel)
        elif not self.visible(area, rel):
            raise AppError("File not found.", 404)

    def filter_listing(self, listing: Dict[str, Any], has_visible_child) -> Dict[str, Any]:
        """Removes the entries the user may not see. A folder that holds only hidden items (e.g. a species whose
        uploads are all private) disappears too: has_visible_child(rel) tells whether anything in it is visible."""
        area, base = listing["area"], listing["path"]
        if self.admin:
            return listing
        out = []
        for e in listing["entries"]:
            rel = f"{base}/{e['name']}" if base else e["name"]
            if area == AREA_GROUPS:
                if base or e["name"].lower() in self.group_folders:
                    out.append(e)
                continue
            if not self.visible(area, rel):
                continue
            if e["type"] == "dir" and self.contains_hidden(area, rel) and not has_visible_child(rel):
                continue
            out.append(e)
        return dict(listing, entries=out)

    # ---- group folders -----------------------------------------------------------
    def group_of(self, rel: str) -> str:
        """The work group whose folder holds `rel` ("<group>/..." or "_pending/<group>/..."); 404 if the user has
        nothing to do with it. An empty name for the root of the area, where everyone sees their own groups only.

        Inside the waiting room the answer is the group as well: who may look there (the sender, an administrator
        of the group) is decided by the storage, which knows the rules of the approvals."""
        parts = [p for p in rel.strip("/").split("/") if p]
        if not parts:
            return ""
        first = parts[0]
        if first == PENDING:                                     # _pending/<group>/<user>/...
            if len(parts) < 2:
                return ""
            first = parts[1]
        if first.startswith("."):
            raise AppError("Folder not found.", 404)
        if self.admin:
            return first                                         # a server administrator opens every folder
        if first.lower() not in self.group_folders:
            raise AppError("Folder not found.", 404)
        return first
