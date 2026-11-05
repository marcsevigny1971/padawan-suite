# -*- coding: utf-8 -*-
"""
Archiveur — conserver localement posts X / Facebook / YouTube (média + texte).
APP_FILE_VER = 5 ; titre fenêtre « Archiveur » sans numéro.
v5: LECTEUR INTÉGRÉ dans l'aperçu (ffmpeg → images + ffplay pour le son, synchro sur l'horloge
    audio ; lecture/pause, ±10 s, barre de position, volume, plein écran ffplay), TRANSCRIPTION
    horodatée cliquable (sous-titres yt-dlp FR/EN, option faster-whisper locale), OUTILS MÉDIA
    (capture, extrait mp4 sans ré-encodage, mp3, GIF → dossier extraits/), PAGES WEB complètes
    (HTML autonome + images, version lecture, texte, liens, capture PNG + PDF pleine page via
    Edge/Chrome headless), posts X (texte, photos, vidéo, fil parent via fxtwitter), FAVORIS et
    COLLECTIONS (filtres app + index global), EXPORT ZIP / CSV / JSON, résumé copiable,
    VÉRIFICATION d'intégrité + réparation, statut EN LIGNE du lien original (🟢/🔴/🟠),
    thèmes Norton/Sombre/Clair + taille de police (Ctrl+molette), multi-sélection et actions
    en lot, statistiques, aide F1, mise à jour yt-dlp, glisser-déposer (tkinterdnd2 optionnel),
    sauvegarde automatique de l'index (rotation), instance unique.
v4.1 (retouches, même fichier v4) : vidéos MP4 compatibles Windows (H.264 + AAC
    préférés à l'archivage, conversion ffmpeg auto si AV1/VP9/Opus, « Convertir en
    MP4 compatible » + « Réparer codecs » + CLI --fix-codecs), lecteur au choix
    (Windows / VLC / mpv détectés), mise en page responsive (barres qui passent à
    la ligne, historique adaptatif, actions sur 2 lignes), file d'attente repliable,
    bandeau codec, infobulles, états des boutons, Ctrl+V global, tests --geometry/--shot.
v4: APERÇU convivial et défilant (barre verticale + molette) : grande miniature
    redimensionnée (clic = lire), storyboard ffmpeg (6 images), carte d'infos
    (plateforme, auteur, dates, durée, taille, résolution, URL cliquable), texte
    du post défilant/copiable, galerie, fichiers (icônes, taille, clic droit),
    barre d'actions (Lire, Original, Page archive, Dossier, Renommer, Copier
    lien, Supprimer), tags + notes perso. Historique : recherche, filtre
    plateforme, tri, compteur, vignettes. File d'attente visible (% yt-dlp,
    annuler), lot « Plusieurs liens », surveillance presse-papiers (option),
    doublons, qualité (Meilleure/720p/480p/Audio mp3), sous-titres FR/EN,
    notifications plyer, paramètres persistants, index global en cartes,
    journal archiveur.log, mises à jour Tk thread-safe (file + after()).
v3: aperçu résultat, renommer (F2), historique clic droit, Coller et archiver
    garde l'URL visible, Ouvrir dossier fiable, titres auto améliorés.
v2: bouton Coller et archiver, Ctrl+V / Shift+Insert / Entrée auto-archivage,
    menu clic droit FR sur le champ URL.
"""

from __future__ import annotations

# --- v1.2.2 : le code est découpé en parties dans archiveur_parties\ (fichiers < 3000 lignes). ---
# Toutes les parties partagent l'espace de noms de ce module : comportement identique
# à l'ancien fichier unique (globals, réglages, données inchangés).
# Version lue par le Tableau de bord : APP_FILE_VER = 5
import os as _os_parties

_PARTIES = ["a01_config.py", "a02_pont_grimoire.py", "a03_index_recherche.py", "a04_medias_ffmpeg.py", "a05_telechargement.py", "a06_codecs_lecteurs.py", "a07_collections.py", "a08_transcription_web.py", "a09_x_verif_export.py", "a10_widgets.py", "a11_app1.py", "a11_app2.py", "a11_app3.py", "a11_app4_assemblage.py", "a12_cli.py"]


def _charger_parties(ns) -> None:
    base = _os_parties.path.join(_os_parties.path.dirname(_os_parties.path.abspath(__file__)), "archiveur_parties")
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
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        setup_logging()
        logger.exception("Erreur fatale")
        try:
            if tk is not None:
                r = tk.Tk()
                r.withdraw()
                messagebox.showerror(APP_NAME, "Erreur au démarrage — détails dans archiveur.log\n\n"
                                     + traceback.format_exc()[-800:])
                r.destroy()
        except Exception:
            pass
        raise
