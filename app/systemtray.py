# -*- coding: utf-8 -*-
"""
systemtray.py — alias / wrapper vers padawan_tray.

Marc cherche « systemtray.py » dans le répertoire d'installation FTP.
Tout le code tray vit dans padawan_tray.py ; ce fichier le réexporte.
"""
from padawan_tray import *  # noqa: F401,F403
from padawan_tray import __all__  # noqa: F401
