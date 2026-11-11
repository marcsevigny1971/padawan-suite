# Journal des versions — Padawan Suite

## v1.3.0 — 2026.11.11 — CaptureScreen : enregistrer l'écran pour enseigner
- Nouveau : CaptureScreen 1.3.0 (`capturescreen1.py` + `capturescreen_parties\`). Écran entier, moniteur, fenêtre ou zone, en MP4 (H.264 + AAC), son de l'ordinateur et/ou micro (module `soundcard`), 15/30/60 i/s. Clics en halo, bulle des touches, caméra en vignette, compte à rebours, pause, barre flottante. Dessin à l'écran, loupe, projecteur, tableau blanc, minuteur, repères. Bibliothèque, coupe rapide, sous-titres (faster-whisper si installé), capture PNG.
- CaptureScreen 1.3.0 : arrêt pile à l'heure (statistiques ffmpeg toutes les 0,25 s), chien de garde qui relance un enregistrement planté ou figé (25 s), réparation d'un morceau abîmé, écran de fin « Bravo ! », test `--test-robustesse`.
- Archiveur : bouton rouge « 🎥 Enregistrer » (la vidéo arrive dans une fiche) ; fiches et aperçus pour 52 sites via le module commun `padawan_embeds.py` (oEmbed/OpenGraph, cache 7 jours, lecteur officiel dans une petite fenêtre). Aucun contournement : contenu protégé = aperçu + lien.
- Padawan : cartes Sources dépliables (`padawan_cartes.py`) ; errors.log tourne au-delà de 2 Mo (errors.log.1).
- Tableau de bord 1.3.0 (suite 1.3.0, 2026.11.11) ; Premiers pas : scénario CaptureScreen ; menu de l'icône : CaptureScreen.
- Installateur : raccourcis CaptureScreen (Bureau + menu Démarrer comme les autres) ; correctif de l'installation silencieuse (`/VERYSILENT`), où `-NoLaunch` en double faisait échouer la configuration.
- Aucune donnée touchée.

## v1.2.5 — 2026.11.05 — Archiveur : contrôles dans la Grande fenêtre
- « ⛶ Grande fenêtre » s'ouvre maintenant avec sa propre barre de contrôles, toujours visible : ▶/⏸ Lecture-Pause, ⏪ 10 s / 10 s ⏩, barre de position (clic ou glisser), temps, 🔊/🔇 et volume, ⛶ Plein écran, ✖ Fermer. Bulle d'aide sur chaque bouton.
- En plein écran, la barre se replie après 3 s sans bouger la souris et revient au moindre mouvement (ou en pause).
- Souris : clic sur l'image = pause/lecture, double-clic = plein écran, molette = volume.
- Clavier : Espace/K = pause, F/F11 = plein écran, Échap = sortir du plein écran puis fermer, ←/→ = ±5 s, Maj+←/→ ou J/L = ±10 s, ↑/↓ = volume, M = muet, Début = retour au début.
- À la fermeture, le petit lecteur reprend à la même position (en pause). Si le lecteur intégré n'est pas disponible, l'ancienne fenêtre ffplay sert de secours.
- Tableau de bord 1.2.5. Aucune donnée touchée.

## v1.2.4 — 2026.11.05 — Archiveur : barre Collections plus compacte
- La barre « Collections » à gauche de l'Archiveur n'a plus de largeur fixe : elle s'ajuste toute seule à ses noms (entre 120 et 280 px, au plus 22 % de la fenêtre), et l'Historique récupère l'espace perdu.
- Une poignée (séparateur) entre Collections et Historique permet de choisir la largeur à la souris ; la largeur choisie est mémorisée (réglage `coll_side_w`).
- Double-clic sur la poignée : retour à la largeur automatique. Le bouton ◀ cache/affiche toujours la barre.
- Tableau de bord 1.2.4. Aucune donnée touchée.

## v1.2.3 — 2026.11.05 — Les thèmes du Journal partout dans la suite
- Nouveau module commun `padawan_themes.py` : les 4 thèmes du Journal de bord (🌌 Cosmos, 📜 Papier, 🌙 Nuit douce, 🌲 Forêt), mêmes noms et mêmes couleurs, plus ✨ Original (le look propre de chaque programme, par défaut : rien ne change tant que tu ne choisis rien).
- Dans Grimoire, Archiveur, Arsenal, Facteur, Messager, Padawan, Gestionnaire, Chantier, Rétro, Coffre, Recherche et Premiers pas : menu « 🎨 Thème » (bulle d'aide) et raccourci Ctrl+Maj+T (thème suivant). Le changement se fait en direct ; les rares détails qui ne suivent pas changent au prochain lancement (un message le dit).
- Tableau de bord : bouton « 🎨 Thème de toute la suite » ; le choix vaut pour tous les programmes, Journal de bord compris.
- Le choix est gardé dans %APPDATA%\Padawan\themes.json (un choix par programme passe avant celui de toute la suite). Aucune donnée touchée.
- Les textes trop pâles sur le thème Papier (ex. couleurs de sujets) sont foncés automatiquement pour rester lisibles.

## v1.2.2 — 2026.11.04 — Archiveur et Grimoire plus robustes (code découpé)
- Archiveur 5 et Grimoire : le code (11 700 et 11 000 lignes dans un seul fichier) est découpé en parties de moins de 2 000 lignes, dans `archiveur_parties\` et `grimoire_parties\`. Plus facile à lire, à corriger et à ouvrir dans un éditeur.
- Aucun changement de fonctionnement : mêmes raccourcis, même icône, mêmes données (grimoire.db, archives, réglages). `archiveur5.py` et `grimoire1.py` restent les fichiers à lancer.
- Vérifié : le code découpé est identique, ligne pour ligne, à l'ancien fichier ; tests automatiques (--smoke, --check, --verify, --stats) identiques avant et après.
- Journal de bord 1.4.3 : correctif du calendrier (1.4.2) et animation d’ouverture retirée (1.4.3).
- Installateur : une mise à jour par `INSTALLER.bat` fusionne maintenant les dossiers au lieu de les imbriquer.

## v1.2.1 — 2026.11.02 — Correctifs Journal et Nouvelle conversation
- Padawan 39.1 : bouton « 🧹 Nouvelle conversation » (Ctrl+L ou Ctrl+Shift+N) qui repart l'esprit clair : chat vidé, contexte du modèle remis à zéro (seulement ses consignes de base), ancienne conversation archivée dans %APPDATA%\Padawan\conversations (rien n'est effacé).
- Padawan 39.1 : « 🕘 Historique » (Ctrl+Shift+H) pour relire les anciennes conversations ; chaque lancement repart aussi sur une conversation neuve.
- Journal de bord 1.4.1 :
  - Une pièce retirée (image, fichier, lien, mémo vocal) ne revient plus après Consigner et rechargement ; son fichier va dans _corbeille du journal.
  - Bouton « ✕ Retirer » sur chaque carte (bulle d'aide), touche Suppr sur une carte sélectionnée.

## v1.2 — 2026.10.31 — Cartes, liens permanents et curseur vivant
- Journal de bord 1.4 : date normale dans le titre, 4 thèmes, animations, modèles, favoris, corbeille, impression/export, série de jours, démarrage intelligent (nouvelle entrée ou quart de nuit), heure ajoutée dans le texte, curseur vivant, aperçus de liens + « Rendre permanent » via l'Archiveur, panneau « Mes liens ».
- Grimoire 1.5 : vue en cartes, carte des sujets animée (F8), aperçus de liens + liens permanents.
- Archiveur : conversion accélérée par la carte graphique (NVENC/QSV/MF, repli processeur), barre de progression, storyboard automatique, collections avec classement suggéré, « Envoyer au Grimoire ».
- Tableau de bord et menu de l'icône réordonnés (outils courants en haut, serveurs en bas), barre de défilement, fenêtres ouvertes agrandies.

## v1.1 — 2026.10.24 — Journal de bord
- Nouveau Journal de bord, Padawan plus vivant (dolphin3:8b), recherche dans le journal.
