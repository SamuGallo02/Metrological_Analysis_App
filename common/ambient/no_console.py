"""No console window, ever (Windows).

Every process the application starts is asked for with CREATE_NO_WINDOW, so nothing black flashes on the screen.
The calls of the application already do that one by one; this covers what we do not write ourselves - pip, the
libraries, a tool a package calls on its own - by setting the flag in `subprocess.Popen` itself.

A process that deliberately wants a console of its own (DETACHED_PROCESS, CREATE_NEW_CONSOLE) is left alone:
those flags cannot be combined, and asking for both makes Windows refuse to start the process.

Autore: Samuele Gallo
"""
from __future__ import annotations

import os
import subprocess

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_CONSOLE = 0x00000010


def hidden_flags(flags: int = 0) -> int:
    """The creation flags to use: the same ones, plus 'no console' when that does not contradict them."""
    if flags & (DETACHED_PROCESS | CREATE_NEW_CONSOLE):
        return flags
    return flags | CREATE_NO_WINDOW


def silence_console() -> None:
    """Hides the console of every process started from now on. Does nothing outside Windows, and nothing at all
    the second time it is called."""
    if os.name != "nt" or getattr(subprocess.Popen, "_console_hidden", False):
        return
    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):                       # noqa: N807 - it replaces a dunder on purpose
        kwargs["creationflags"] = hidden_flags(kwargs.get("creationflags", 0))
        original(self, *args, **kwargs)

    __init__.__doc__ = original.__doc__
    subprocess.Popen.__init__ = __init__
    subprocess.Popen._console_hidden = True
