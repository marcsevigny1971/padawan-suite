================================================================================
  PROJET PADAWAN — guide complet
  Pour Marc (et pour un ami qui installe le kit)
  Date : 12 octobre 2026
================================================================================

VUE D'ENSEMBLE
--------------
Le Projet Padawan, c'est une petite famille d'outils Python sur ton PC,
avec UNE seule icône dans la barre système (le tray) : Padawan.

  Padawan          — assistant (Ollama), conversation, démarrage Windows
  Tray             — menu : ouvrir les autres outils, démarrer avec Windows
  Gestionnaire     — explorateur de fichiers maison
  Archiveur        — archive vidéos / pages web dans FTP_HOME\ARCHIVEUR
  Arsenal          — tiroir à outils (commandes, scripts, Defender…)
  Grimoire         — carnet de recherche par sujets (notes, liens, médias)
  Facteur          — surveille des dossiers + commandes à distance / Boîte SQL

Tout le code vit sous :
  C:\web\FTP_HOME\SECTION PYTHON\Projet Padawan\

Les données (donc tes backups) :
  C:\web\FTP_HOME\ARCHIVEUR\
  C:\web\FTP_HOME\GRIMOIRE\
  C:\web\FTP_HOME\FACTEUR\
  (+ arsenal.json à côté des programmes)


================================================================================
  CHAQUE PROGRAMME
================================================================================

1) PADAWAN (padawan39.py)
-------------------------
À quoi ça sert : ton assistant local (Ollama), fenêtre plein écran, thèmes
Norton / Sombre / Clair.

Fonctions principales :
  • Discussion avec le modèle (ex. dolphin3:8b)
  • Mémoire / config dans le dossier du projet
  • Lance le tray ; option « Démarrer avec Windows » (une seule clé HKCU Run)

Raccourcis (repères) : F1 aide si présent ; Esc / X → masque dans le tray
(ne quitte pas — « Quitter Padawan » dans le menu tray).

Données : config.json, memory.json, tasks.json à côté de padawan39.py
Fichier : padawan39.py


2) TRAY (padawan_tray.py + systemtray.py)
-----------------------------------------
À quoi ça sert : l'icône unique Padawan dans la zone de notification.

Menu typique :
  Padawan — Ouvrir / Masquer
  Gestionnaire de fichiers…
  Archiveur…
  Arsenal…
  Grimoire…
  Facteur…
  Démarrer avec Windows
  Quitter Padawan

Au démarrage, le tray lance aussi Facteur en mode --cache (moteur actif,
fenêtre cachée), sans deuxième icône.

Fichiers : padawan_tray.py, systemtray.py (alias), padawan_tray.ico


3) GESTIONNAIRE DE FICHIERS (gestionnaire_fichiers5.py)
-------------------------------------------------------
À quoi ça sert : naviguer et gérer des fichiers dans le style Padawan.

Fonctions : parcours de dossiers, actions de base sur les fichiers.
Données : pas de grosse base dédiée (travail sur le disque).
Fichier : gestionnaire_fichiers5.py


4) ARCHIVEUR (archiveur5.py)
----------------------------
À quoi ça sert : archiver des vidéos (yt-dlp), posts, pages web, avec
métadonnées, storyboard, lecteur intégré.

Fonctions principales :
  • Coller une URL → archive dans FTP_HOME\ARCHIVEUR
  • Qualité, sous-titres, tags, notes, recherche
  • Envoi vers le Grimoire (clic droit selon version)

Raccourcis / CLI utiles :
  --url …   --smoke   --geometry 1024x576   --shot fichier.png

Données : C:\web\FTP_HOME\ARCHIVEUR\
Fichier : archiveur5.py (repli v4/v3… si besoin)


5) ARSENAL (arsenal1.py)
------------------------
À quoi ça sert : lancer d'un clic tes outils, scripts, scans Defender,
raccourcis Padawan, etc.

Fonctions : catégories, favoris, confirmation, mode admin, capture de sortie,
variables {PROJET} {PYTHONW} {MPCMDRUN}…

CLI : --check  --list  --run-capture  --make-icons  --smoke

Données : arsenal.json (à côté du programme, donc dans les backups de C:\web)
Fichier : arsenal1.py


6) GRIMOIRE (grimoire1.py)
--------------------------
À quoi ça sert : ton carnet de recherche par sujets (le « dump » classé :
notes, liens, images, PDF, sons, mémos vocaux, citations…).

Fonctions principales :
  • Arbre de sujets / sous-sujets (créer, renommer, fusionner, corbeille)
  • Ctrl+V intelligent, glisser-déposer, modèles de fiches
  • Recherche Ctrl+F, vues liste / cartes / chronologie, mode lecture
  • --ajouter / --importer-lot depuis Facteur ou l'Archiveur

Raccourcis : Ctrl+F recherche, Ctrl+Maj+G gérer les sujets, F1 aide,
F2 renommer (selon version).

Données : C:\web\FTP_HOME\GRIMOIRE\ (grimoire.db SQLite, medias\, _sauvegardes\)
Fichier : grimoire1.py  (+ grimoire_depart.db pour une install neuve)


7) FACTEUR (facteur1.py + facteur_boite.py)
------------------------------------------
À quoi ça sert : voir facteur_readme.txt (détail complet).

En bref :
  • Surveille Téléchargements + règles + journal
  • Commandes .padawan signées
  • Boîte SQL via pont PHP (voyage) — onglet Boîtes SQL
  • Sources web : web_sources\*.php.txt (deployer hors FTP_HOME, jamais sous FTP_HOME)

Données : C:\web\FTP_HOME\FACTEUR\
Clé : %LOCALAPPDATA%\Padawan\Facteur\facteur_cle.dpapi
Fichiers : facteur1.py, facteur_boite.py, web_sources\, scripts\


================================================================================
  ARBORESCENCE (repères)
================================================================================

C:\web\FTP_HOME\
  ARCHIVEUR\                 ← vidéos / pages archivées
  GRIMOIRE\                  ← base + médias du carnet
  FACTEUR\                   ← config, journal, _Traités, _Quarantaine
  DESCRIPTION\Padawan\       ← copies + descriptions + installateurs
  SECTION PYTHON\
    Projet Padawan\          ← TOUS les .py, setup, icônes, web\, _distribution\
    Archiveur\  Arsenal\  Grimoire\  Facteur\   ← copies / vitrines
    …

Projet Padawan\_distribution\
  Padawan-Setup.exe          ← installateur un fichier
  Padawan-Projet.zip         ← secours (INSTALLER.bat)


================================================================================
  INSTALLATION
================================================================================

Sur CE PC (déjà en place) :
  setup_padawan.bat
  → Python si besoin, pip (requirements-padawan.txt), ffmpeg, raccourcis
    Bureau, clé Run « Padawan », option Ollama.

Pour un ami :
  1) Télécharger Padawan-Setup.exe (ou le .zip)
  2) Double-clic (si SmartScreen → Informations complémentaires → Exécuter)
  3) Suivre les questions (Ollama O/N…)
  4) Relancer la session ou lancer Padawan

Désinstallation :
  Desinstaller.bat / desinstaller_padawan.ps1
  (retire raccourcis + clé Run ; ne casse pas tout C:\web)


================================================================================
  DÉMARRAGE AUTOMATIQUE ET TRAY
================================================================================
- Une seule entrée : HKCU\…\Run\Padawan → pythonw padawan39.py
- Pas de doublon Startup\Padawan.bat / .lnk (nettoyés par le setup)
- Une seule icône tray : Padawan
- Facteur démarre en --cache via le tray (pas d'icône Facteur en plus)


================================================================================
  SAUVEGARDES
================================================================================
Ton backup.bat copie tout C:\web vers E: et D:.
Donc Padawan + Archiveur + Grimoire + Facteur + DESCRIPTION sont inclus.

Conseil : ferme Grimoire / Facteur avant un backup pour une copie bien propre
de leurs fichiers (surtout grimoire.db).


================================================================================
  DÉPENDANCES (résumé)
================================================================================
Python 3 (pythonw), pip packages dans requirements-padawan.txt :
  Pillow, pystray, plyer, requests, yt-dlp, beautifulsoup4, tkinterdnd2,
  pypdf, sounddevice, soundfile, numpy, watchdog, pywin32, pymysql, …
Optionnel : Ollama + modèle, faster-whisper, ffmpeg (winget Gyan.FFmpeg), VLC.


================================================================================
  DÉPANNAGE
================================================================================
• Tray absent → pip install pystray pillow ; relancer Padawan
• Deux Padawan → Quitter via le tray, vérifier qu'il n'y a qu'une clé Run
• Archiveur sans son → ffplay / paquet ffmpeg complet
• Grimoire ne reçoit pas --ajouter → s'il est déjà ouvert, ça passe par _inbox
• Facteur / Boîte SQL → voir facteur_readme.txt (clé, URL du pont, PASS)


================================================================================
  VERSIONS DES FICHIERS (instantané du 2026-10-12)
================================================================================
Fichier                        Taille (octets)   Modifié (approx.)
-----------------------------  ----------------  -------------------
padawan39.py                   199512            2026-10-05
padawan_tray.py                28187             2026-10-12
gestionnaire_fichiers5.py      48051             2026-10-02
archiveur5.py                  465727            2026-10-12
arsenal1.py                    366003            2026-10-12
grimoire1.py                   450512            2026-10-12
facteur1.py                    ~163000           2026-10-12
facteur_boite.py               ~19000            2026-10-12
setup_padawan.bat              ~14000            2026-10-12
Padawan-Setup.exe / .zip       voir _distribution\ (reconstruire après MAJ)

Page test Boîte SQL (nom difficile à deviner) :
  web_sources\ (sources PHP en .txt, hors FTP_HOME)

Pour le détail Facteur (règles, .padawan, Boîte SQL, 5 étapes web) :
  → facteur_readme.txt

FACTEUR AU DEMARRAGE DE WINDOWS
-------------------------------
Facteur demarre tout seul, en arriere-plan (--cache, sans fenetre), a l'ouverture de Windows
(cle HKCU Run "Facteur"). Une seule instance : s'il roule deja, le tray Padawan n'en relance pas un 2e.
Pastille dans le menu du tray Padawan : VERT = Facteur actif, JAUNE = passif.
Pour le DESACTIVER : clic sur l'icone Padawan (tray) > clic sur "Facteur : actif" (devient jaune :
  Facteur s'arrete ET ne demarre plus avec Windows). Re-clic = actif (vert) + demarrage auto.
  ou dans Facteur : menu Fichier > decocher "Demarrer avec Windows".
Pour le reactiver : recocher. Le choix est memorise (meme apres reinstallation).
Pour l'arreter tout de suite : Facteur > Fichier > Quitter Facteur.

VOIX (LECTURE A HAUTE VOIX)
---------------------------
Onglet Distant de Facteur : case lire a voix haute, liste de voix (Auto = fr-CA
en priorite), bouton Tester. Voir facteur_readme.txt.

NOUVEAU (21 oct. 2026) : Chantier (chantier1.py) - serveurs web/SQL/FTP/MQTT a la demande, voir LISEZMOI-CHANTIER.txt.
Retro (retro1.py) - lanceur C64/DOS/Win98, voir LISEZMOI-RETRO.txt. Les deux sont dans le menu de l'icone Padawan.

RESSOURCES / GITHUB
-------------------
La Padawan Suite a sa page publique sur GitHub :
  Page du projet      : https://github.com/marcsevigny1971/padawan-suite
  Mises a jour        : https://github.com/marcsevigny1971/padawan-suite/releases/latest
  Idees, suggestions  : https://github.com/marcsevigny1971/padawan-suite/issues
  Presentation        : https://marcsevigny1971.github.io/padawan-suite/
Raccourcis : icone Padawan > "Ressources / GitHub", Premiers pas (en bas), Arsenal > Web pratique.
