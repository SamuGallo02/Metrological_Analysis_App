"""Lists all translatable texts in the code: first literal argument of tr(), N_(), AppError(), ApiError()...

    python -m tools.extract_strings            # prints the count and the texts
Non-literals (tr(variable)) are reported: they must be made literal or passed to tr_dyn().
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("common", "corpse", "server")
CALLS = {"tr", "N_", "AppError", "ApiError", "OfflineError", "Cancelled"}


def extract(root: Path = ROOT) -> Tuple[Set[str], List[str]]:
    keys: Set[str] = set()
    problems: List[str] = []
    for pkg in PACKAGES:
        for path in sorted((root / pkg).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                if name not in CALLS:
                    continue
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    keys.add(arg.value)
                elif name in ("tr", "N_"):
                    problems.append(f"{path.relative_to(root)}:{node.lineno}: {name}() with a non-literal text")
    return keys, problems


if __name__ == "__main__":
    k, p = extract()
    print(f"{len(k)} strings", file=sys.stderr)
    for line in p:
        print("WARNING", line, file=sys.stderr)
    for s in sorted(k):
        print(s)
