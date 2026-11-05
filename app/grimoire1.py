# -*- coding: utf-8 -*-
"""
Grimoire 1 - carnet de recherche par sujets (Projet Padawan).

Le « dump de tout » de Marc, classe par sujets et sous-sujets :
- notes en texte riche (gras, italique, titres, listes, cases a cocher, citations, liens cliquables,
  references [[...]] entre fiches), modeles de fiches (source, protocole, plante, recette...) ;
- liens web (titre, description et miniature recuperes), videos/embeds (YouTube, X, TikTok...),
  citations avec source, captures de pages web completes (HTML hors ligne + PDF + image) ;
- images (vignettes, visionneuse zoom, OCR Windows optionnel), documents (PDF, Word, texte... :
  texte extrait pour la recherche), sons (lecture ffplay cachee), memos vocaux enregistres dans
  l'application (transcription faster-whisper optionnelle), fichiers quelconques ;
- recherche plein texte instantanee (SQLite FTS5, sans accents) avec filtres et surlignage,
  vues liste / cartes / chronologie, mode lecture, favoris, epingles, etiquettes, corbeille,
  Ctrl+Z, glisser-deposer, Ctrl+V intelligent, export HTML autonome / ZIP, import de dossier,
  statistiques, sauvegardes automatiques, ligne de commande --ajouter / --importer-lot pour la famille Padawan.

Donnees : C:\\web\\FTP_HOME\\GRIMOIRE\\ (grimoire.db, medias\\<sujet>\\, _sauvegardes\\, _inbox\\,
grimoire.log) : tout est pris par backup.bat.
Tests : --smoke, --check, --shot fichier.png --geometry 1280x720 --shot-view main|cartes|chrono|recherche|...
"""

from __future__ import annotations

# --- v1.2.2 : le code est découpé en parties dans grimoire_parties\ (fichiers < 3000 lignes). ---
# Toutes les parties partagent l'espace de noms de ce module : comportement identique
# à l'ancien fichier unique (globals, réglages, données inchangés).
# Version lue par le Tableau de bord : APP_FILE_VER = 1
import os as _os_parties

_PARTIES = ["g01_base.py", "g02_stockage.py", "g03_web_medias.py", "g04_contenu.py", "g05_widgets.py", "g06_editeur.py", "g07_carte.py", "g08_app1.py", "g08_app2.py", "g08_app3.py", "g08_app4_assemblage.py", "g09_cli.py"]


def _charger_parties(ns) -> None:
    base = _os_parties.path.join(_os_parties.path.dirname(_os_parties.path.abspath(__file__)), "grimoire_parties")
    for nom in _PARTIES:
        chemin = _os_parties.path.join(base, nom)
        try:
            with open(chemin, "r", encoding="utf-8") as fh:
                code = fh.read()
        except OSError as e:
            raise ImportError(f"Partie manquante : {chemin} ({e}). Réinstalle Padawan (Padawan-Setup.exe).") from e
        exec(compile(code, chemin, "exec", dont_inherit=True), ns)


_charger_parties(globals())


if __name__ == "__main__":
    sys.exit(main())
