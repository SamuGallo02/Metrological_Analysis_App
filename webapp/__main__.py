"""python -m webapp  serve | ...  — the same commands as `python -m server` (create-admin, backup, users...);
`serve` also gives the web pages on "/" and the analysis on the server.

    python -m webapp create-admin NAME
    python -m webapp serve                      # then open http://127.0.0.1:8765 in the browser
"""
import sys

from server.__main__ import main

from .handler import WebHandler

if __name__ == "__main__":
    sys.exit(main(handler_base=WebHandler))
