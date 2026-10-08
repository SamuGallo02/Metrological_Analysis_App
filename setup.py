"""Compatibilita': l'installazione e' ora gestita dal pacchetto installer/."""
import sys

from installer.runner import main

sys.exit(main(sys.argv[1:]))
