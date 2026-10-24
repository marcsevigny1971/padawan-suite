================================================================================
  FACTEUR — mode d'emploi (Projet Padawan)
  Date : 12 octobre 2026
================================================================================

À QUOI ÇA SERT
--------------
Facteur, c'est le « facteur » de ton PC : il surveille des dossiers (surtout
Téléchargements) et applique tes règles quand un fichier arrive.

Exemple : tu es en voyage, tu ouvres une petite page web sur ton téléphone,
tu écris un message, tu envoies. Sur ton PC à la maison, Facteur reçoit le
message, affiche une notification Windows (et peut le lire à voix haute),
et ouvre sa fenêtre pour que tu le voies au retour.

Il sert aussi à trier Téléchargements, copier des fichiers, envoyer un lien
au Grimoire ou à l'Archiveur, et lancer des programmes ou scripts que TU as
mis dans une liste blanche locale (alias publics inoffensifs, ou commandes
nommées réservées au mode admin web).


1) DOSSIERS SURVEILLÉS
----------------------
- Par défaut : ton vrai dossier Téléchargements (Windows le trouve tout seul).
- Tu peux en ajouter d'autres. Chaque dossier a son intervalle ; le mode
  événementiel (watchdog) réagit tout de suite. Pause possible par dossier.


2) RÈGLES (Quoi / Quand / Quoi faire)
-------------------------------------
Chaque règle dit QUOI (masques, extensions…), QUAND (horaire, jours),
et QUOI FAIRE (déplacer, copier, notifier, Grimoire, Archiveur, ligne CMD
ou PowerShell QUE TOI tu as écrite dans Facteur).

IMPORTANT : les lignes de commande libres existent SEULEMENT dans tes règles
locales. Elles ne viennent JAMAIS d'un fichier reçu par Internet (.padawan)
ni de la Boîte SQL.


3) APRÈS TRAITEMENT
-------------------
Le fichier original part dans le dossier de données Facteur\_Traités\AAAA-MM-JJ\
(sauf s'il a déjà été déplacé). Empreinte anti-doublon. Refus → _Quarantaine\


4) COMMANDES À DISTANCE (.padawan)
----------------------------------
Un fichier .padawan = JSON signé HMAC-SHA256 avec ta clé secrète.

Actions autorisées à distance (liste blanche) :
  grimoire_ajouter, archiver_lien, lancer_raccourci_arsenal,
  lancer_programme_autorise, copier_vers, notifier

Sécurité : signature, expiration, anti-rejeu, liste blanche.
Clé protégée par Windows (DPAPI) dans %LOCALAPPDATA%\Padawan\Facteur\
(pas en clair, jamais dans FTP_HOME).

Facteur → onglet Distant → Afficher / copier la clé (UNE seule fois).


5) BOÎTE SQL (quand tu es ailleurs)
-----------------------------------
Ta page web écrit une ligne dans MySQL sur TON serveur. Facteur lit via un
pont PHP en HTTPS. Sur le PC : AUCUN mot de passe MySQL — seulement l'URL
HTTPS du pont dans Facteur → Boîtes SQL.

Intervalle de vérification Boîte SQL : 15 secondes par défaut (léger).


6) LES ÉTAPES POUR LA PAGE WEB
------------------------------
1) Facteur → Boîtes SQL → « Exporter les pages web »
   (écrit aussi facteur_cle.php avec la clé HMAC)

2) Sur le SERVEUR (hors FTP_HOME, ex. C:\web\facteur\) :
   ouvre facteur_boite_config.php et remplis SEULEMENT $LOCAL_DB_PASS.
   Les sources livrées avec Padawan sont dans web_sources\ en .txt
   (à renommer en .php sur le serveur). JAMAIS de .php sous FTP_HOME
   (tout y est téléchargeable).

3) Dépose le pont en HTTPS chez ton hébergeur (dossier web dédié, pas FTP_HOME).

4) Facteur → Boîtes SQL → Ajouter → colle l'URL du pont
   https://ton-site.exemple/.../facteur_boite.php
   Active, « Créer les tables », « Tester le pont ».

5) Page de TEST : copie le modèle facteur_test_TEMPLATE, renomme-le avec un
   nom aléatoire difficile à deviner, ne publie pas l'URL.
   Sans mot de passe admin : notification (et alias publics inoffensifs).
   Avec mot de passe admin (hash côté serveur) : commandes nommées réservées.


7) ALIAS ET COMMANDES NOMMÉES
-----------------------------
Dans Facteur → onglet Distant :
  - Alias locaux (publics) : paint, notepad, calc, pbrush… → programmes simples
  - Commandes nommées (admin web seulement) : apache, backup, verrouiller, site…
    Type exe / cmd / PowerShell. Tu peux en ajouter autant que tu veux.
  Les scripts d'exemple (restart_xampp.cmd, backup_web.exemple.cmd) sont
  copiés dans le dossier de données Facteur\scripts\ à l'installation.


8) VOIX (LECTURE À HAUTE VOIX)
------------------------------
Onglet Distant :
  - case « Lire les messages à voix haute » (lit les popups reçus) ;
  - liste « Voix » : Auto (français en priorité = fr-CA puis fr-*, sinon anglais)
    ou une voix précise installée sur le PC ;
  - bouton « Tester » : dit une courte phrase avec la voix choisie.

Voix Windows / OneCore (ex. Microsoft Caroline / Claude, français Canada)
quand elles sont installées. Pour ajouter fr-CA :
  Paramètres Windows → Heure et langue → Parole (ou Voix) → Ajouter des voix.


9) FACTEUR AU DÉMARRAGE DE WINDOWS
----------------------------------
Facteur démarre tout seul en arrière-plan (--cache, sans fenêtre) à l'ouverture
de Windows (clé HKCU Run « Facteur »). Une seule instance.

Pastille dans le menu du tray Padawan :
  VERT = Facteur actif ; JAUNE = passif.
Clic sur « Facteur : actif/passif » : démarre/arrête ET active/désactive le
démarrage avec Windows. Ou dans Facteur : menu Fichier → « Démarrer avec Windows ».
Le choix est mémorisé (même après réinstallation).


10) JOURNAL, PAUSE, TABLEAU DE BORD
-----------------------------------
Journal filtrable + facteur.log ; pause globale ; tableau de bord.


11) OÙ SONT LES DONNÉES
-----------------------
  Si C:\web\FTP_HOME existe : C:\web\FTP_HOME\FACTEUR\
  Sinon : %USERPROFILE%\Documents\Padawan\Facteur\
    facteur_config.json   (créé au 1er lancement ; boites_sql vide par défaut)
    facteur.log
    scripts\
    _Traités\   _Quarantaine\

  Clé HMAC (DPAPI, générée au 1er lancement) :
    %LOCALAPPDATA%\Padawan\Facteur\facteur_cle.dpapi

  Programme (après install) : à côté de padawan39.py
  Sources web (lecture seule) : web_sources\*.php.txt


12) DÉPANNAGE
-------------
Q : Message envoyé, rien sur le PC ?
A : Facteur tourne-t-il (tray Padawan pastille verte, ou Facteur --cache) ?
   Boîte SQL active ? URL du pont bonne ? Voir le journal.

Q : « signature invalide »
A : Ré-exporte les pages depuis Facteur et redépose facteur_cle.php sur le serveur.

Q : « LOCAL_DB_PASS vide »
A : Remplis le mot de passe dans facteur_boite_config.php sur le serveur.

Q : Deux icônes dans le tray ?
A : Une seule doit rester : Padawan. Quitte via le tray et relance.

Q : Voix en anglais seulement ?
A : Installe une voix française (Canada) dans Paramètres Windows, puis relance Facteur.


Fichiers utiles
---------------
  facteur1.py, facteur_boite.py, facteur_readme.txt, LISEZMOI-FACTEUR.txt,
  LISEZMOI-BOITE-SQL.txt, web_sources\, scripts\
