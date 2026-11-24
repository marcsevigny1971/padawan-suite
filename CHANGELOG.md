# Journal des versions — Padawan Suite

## v1.6.0 — 2026.11.23 — 🎨 Studio, 🖼 ANSI et 💻 Atelier 1.4
- Padawan v40.0 → v41.2.
- 🎨 **Studio d'images** (`Ctrl+G`, module `padawan_studio.py`, v41.0) : ComfyUI local + SD-Turbo démarré à la demande sur 127.0.0.1, idée FR → prompt EN par le modèle courant, 6 styles, graine, variations, image + art ANSI côte à côte, export .png/.ans/.html, galerie, partage de la VRAM avec Ollama. ComfyUI et les modèles d'images ne sont pas inclus.
- 🖼 **ANSI** (module `padawan_ansi.py`, v40.1–v40.2) : 🖼→ANSI dans l'Atelier (16 couleurs DOS, truecolor, ASCII, Pip-Boy, ░▒▓█ ; .ans + SAUCE, .txt, HTML). Jeux illustrés : 31 scènes originales (`padawan_jeux_images.json.gz`), effet CRT, clic = agrandir, bouton 🖼 Images (Banque / Générées / Fixes / NON).
- 💻 **Atelier 1.4** : les demandes de modification dans le chat modifient le vrai fichier (lignes numérotées, recalage des numéros, SEARCH/REPLACE accepté), garde-fou anti-fragment avec une relance, couleurs du fichier nommées pour le modèle, aperçu sur « montre-moi le résultat », diff avec gros boutons Appliquer/Refuser. 📎 Insérer un fichier (`Ctrl+I`, glisser-déposer : au curseur, joint au chat, ou onglet), tous encodages, binaires refusés. Gros fichiers joints en partie avec avis. Copie de récupération des onglets non enregistrés.
- 🎮 Jeux (v41.1) : jamais de modèle « coder » en jeu (bascule temporaire dolphin3:8b), relance automatique si réponse coupée ou sans choix, ▶ Continuer + choix de secours. v41.2 : Atelier et Studio s'ouvrent en pleine partie (pause + sauvegarde).
- 📦 **Archiveur 5.1** : liens Google/YouTube normalisés (vid: dans le fragment, /url?q=, youtu.be, m., music., shorts, embed, nocookie), yt-dlp mis à jour chaque semaine et après un échec (nouvel essai), erreurs en français clair, 🧩 Embed (iframe YouTube ou lecteur local `lecteur.html`).
- Tableau de bord 1.6.0 (suite 1.6.0, 2026.11.23). La construction du setup refuse aussi ComfyUI, les modèles d'images et les réglages du Studio.

## v1.5.0 — 2026.11.18 — 💻 Atelier du programmeur
- Padawan v39.6 → v40.0.
- 💻 **Atelier** (`Ctrl+K`, module `padawan_atelier.py`) : mode programmeur plein écran. Chat à gauche (le modèle de code `qwen2.5-coder` s'active le temps de l'Atelier, puis le modèle d'avant revient), éditeur à droite : onglets, numéros de ligne, coloration HTML/CSS/JS/Python/PHP/Arduino/JSON, recherche/remplacement, annuler/rétablir propres, mini-carte.
- Aperçu : page HTML dans le navigateur avec rechargement automatique (petit serveur 127.0.0.1 seulement), Python exécuté dans un panneau, PHP via `php -S` local s'il est présent. 🩺 « Corriger l'erreur » renvoie la trace au modèle.
- Le code proposé par l'IA passe par un **diff** (accepter/rejeter morceau par morceau) ; toute écriture fait d'abord une copie `.bak`.
- Déploiement : dossier Python, dossier Web local, ou serveur FTP / FTPS / SFTP (mot de passe chiffré par Windows, empreinte du serveur vérifiée). Projets, modèles de départ, snippets, outils. Réglages privés dans `atelier.json` / `atelier_projets.json` (jamais dans le setup).
- 📋 **Copier/coller partout** : bouton « 📋 Copier le code » et « 💻 Ouvrir dans l'Atelier » sous chaque bloc de code des réponses, menu clic droit (couper, copier, coller, tout sélectionner) dans les zones de texte, collage multiligne sans envoi accidentel. Le Chercheur suggère l'Atelier quand une demande ressemble à du code.
- 🧠 **Gestionnaire de modèles** (`Ctrl+M`, module `padawan_modeles.py`, v39.6–39.7) : diagnostic de la machine (carte graphique et VRAM, RAM, processeur, disque), mes modèles (activer, effacer), catalogue intégré (mise à jour facultative depuis ollama.com), installation en un clic avec progression et annulation, banc d'essai côte à côte (temps, jetons/s). Recommandations cliquables (⬇ Installer / ⭐ Activer) et bouton par ligne au catalogue. Un prompt ou un jeu peut avoir son propre modèle.
- 🎮 Correctifs du chargement des modèles (v39.8) : un clic dans un jeu n'est plus jamais perdu pendant le chargement (file d'attente, repli sur dolphin3), gemma2 ne se charge plus deux fois (même taille de contexte), statut de chargement chronométré, la Mission est vidée en mode jeu, compatibilité des modèles recalibrée sur des mesures réelles.
- Tableau de bord 1.5.0 (suite 1.5.0, 2026.11.18). La construction du setup refuse aussi les réglages de l'Atelier et du gestionnaire de modèles.

## v1.4.0 — 2026.11.17 — Padawan : prompts, jeux et briefings
- Padawan v39.3 → v39.5.
- 📜 Panneau Prompts (`Ctrl+P`) : favoris modifiables, un prompt actif par rôle, en mode « remplacer » ou « ajouter » ; copie de sécurité avant chaque écriture.
- 🎮 Jouer : Fallout, Polar, Donjon et « Créer un jeu ». Pip-Boy (PV, RAD, faim, soif, quêtes, inventaire). L'inventaire et les barres se mettent à jour même si le modèle formate mal son bloc de statut (lecteur tolérant et indices tirés du récit), les dés d20 pèsent sur les barres, le récit est au « tu ». Parties sauvegardées ; option « Rouvrir la dernière partie au démarrage » (désactivée par défaut).
- 📰 Nouvelles : briefings « 🌍 Géopoliticologue du futur » et « 🔭 Découvertes & avancées ». Recherche web, sources datées et citées, faits séparés de l'interprétation, passages douteux marqués « ⚠ à vérifier ». Modes Hier / Cette semaine / « Ce qui a changé », Régénérer, export HTML. Avec un petit modèle local, la qualité varie.
- Démarrage : Padawan s'ouvre de nouveau sur le Chercheur, avec le prompt par défaut.
- Réglages et état privés hors du dossier des programmes : `%APPDATA%\Padawan` (Padawan) et `%APPDATA%\Padawan\<App>` (Arsenal, Archiveur, Facteur, journal du Grimoire), ou `C:\web_private\<App>` s'il existe. Migration automatique au démarrage : copie, puis l'ancien fichier est rangé dans `bak\config_move_<date>` (jamais effacé, jamais écrasé). Outil commun `padawan_commun.private_dir()` / `migrate_private()`.
- Tableau de bord 1.4.0 (suite 1.4.0, 2026.11.17). La construction du setup refuse maintenant les réglages et l'état privés.
- Archives, Grimoire et vidéos : inchangés.

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
