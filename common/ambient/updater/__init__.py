"""Code integrity and updates of the installed application (standard library only).

* manifest.py  : record of the installed code (version + size/SHA-256 of every file) and its verification
* source.py    : where the code comes from (GitHub archives, single files) and how it is read
* versions.py  : latest version published on GitHub (release if there are releases, else the branch head)
* apply.py     : repair (only the damaged files) and update (only the changed files)
* startup.py   : what main.py does before importing anything heavy
* __main__.py  : `python -m common.ambient.updater status|check|update|repair|mode`

Nothing here imports Qt or the scientific libraries, so it also works when those are damaged.
"""
