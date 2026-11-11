# -*- coding: utf-8 -*-
"""
CaptureScreen 1 - enregistreur d'ecran convivial du Projet Padawan (comme un mini OBS, pour enseigner).

- Enregistre l'ecran entier, un moniteur, une zone tracee a la souris ou une fenetre, en MP4 (H.264 + AAC),
  avec le son de l'ordinateur et/ou le micro, 15/30/60 images/s, qualite au choix.
- Clics de souris en halo de couleur, bulle des raccourcis clavier (rien n'est jamais ecrit sur disque),
  camera en vignette, compte a rebours 3-2-1, Pause/Reprendre, barre flottante (cachee de la video).
- Pour enseigner : dessin a l'ecran (crayon, surligneur, fleches, cadres, texte, gomme), loupe, projecteur,
  tableau blanc/noir, minuteur a l'ecran ; prereglages Cours / Tutoriel / Zone.
- Apres : bibliotheque avec miniatures, ouvrir, dossier, renommer, coupe rapide debut/fin, sous-titres .srt
  (faster-whisper, si installe), envoyer a l'Archiveur, Corbeille.
- Capture d'ecran PNG (ecran / zone / fenetre) copiee dans le presse-papiers.
Enregistre ce que Windows affiche, sans contourner aucune protection anticopie.
Videos : C:\\web\\FTP_HOME\\CAPTURES (modifiable). Reglages : C:\\web_private\\CaptureScreen.
Raccourcis globaux : Ctrl+Maj+R enregistrer/arreter, P pause, S capture, D dessin, L projecteur, Z loupe,
B tableau, M minuteur. F1 aide, Ctrl+Maj+T theme.
"""
VERSION = "1.3.0"
APP_FILE_VER = 1
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capturescreen_parties.c10_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
