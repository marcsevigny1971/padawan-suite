# -*- coding: utf-8 -*-
"""CaptureScreen - c09b : actions (enregistrer, pause, arreter, captures, outils a l'ecran, recuperation,
surveillance de l'espace disque, aide). Messages simples, sans jargon."""
from __future__ import annotations

import os
import shutil
import threading
import tkinter as tk
from tkinter import messagebox

from .c01_config import PRESETS, TMP_DIR, hms, human_size, logger, save_cfg
from .c02_win32 import IS_WIN, bring_to_front, cursor_pos, monitor_of_point, monitors, virtual_screen, window_rect
from .c04_recorder import Recorder, assemble, free_bytes, leftovers, screenshot
from .c05_overlays import RegionBorder, Spotlight, countdown, pick_window, select_region
from .c06_annotate import Annotator
from .c07_controlbar import ControlBar
from .c11_archiveur import video_name, write_result

WARN_FREE = 5 * 1024 ** 3


class Actions:
    # ---------------------------------------------------------- source
    def _source_changed(self):
        s = self.cfg.get("source")
        if s == "zone":
            r = self.cfg.get("region")
            txt = f"\u25ad Zone : {r[2]}×{r[3]} à ({r[0]}, {r[1]})" if r else "\u25ad Zone : pas encore choisie (on te la demandera)"
        elif s == "fenetre":
            txt = f"\U0001fa9f Fenêtre : {self.cfg.get('window_title') or 'pas encore choisie (on te la demandera)'}"
        elif s == "moniteur":
            ms = monitors(); m = ms[min(int(self.cfg.get("monitor") or 0), len(ms) - 1)]
            txt = "\U0001f4fa " + m["label"]
        elif s == "son":
            txt = "\U0001f3a4 Son seulement : " + (" + ".join(x for x, k in (("son de l'ordi", "sys_audio"), ("micro", "mic"))
                                                         if self.cfg.get(k)) or "active « Son de l'ordi » ou « Micro »") + \
                  f" → fichier {str(self.cfg.get('audio_fmt') or 'm4a').upper()}"
        else:
            txt = "\U0001f5a5 Tout l'écran (celui où se trouve la souris)"
        try:
            self.src_lab.configure(text=txt)
            self._mark_tiles()
        except Exception:
            pass

    def set_source(self, src):
        self.cfg["source"] = src; save_cfg(self.cfg)
        if "source" in self.vars:
            self.vars["source"].set(src)
        self._source_changed()
        if src == "zone":
            self.choose_region()
        elif src == "fenetre":
            self.choose_window()

    def apply_preset(self, k):
        self.cfg.update(PRESETS[k]["set"]); self.cfg["last_preset"] = k; save_cfg(self.cfg)
        for key, v in self.vars.items():
            if key in PRESETS[k]["set"]:
                try:
                    v.set(PRESETS[k]["set"][key] if isinstance(v, tk.BooleanVar) else str(PRESETS[k]["set"][key]))
                except Exception:
                    pass
        self._source_changed()
        self.status(f"\u2728 Préréglage : {PRESETS[k]['label']}")
        src = self.cfg["source"]
        if src == "zone" and not self.cfg.get("region"):
            self.choose_region()
        elif src == "fenetre":
            self.choose_window()

    def choose_region(self, then=None):
        self.root.withdraw()

        def done(r):
            self.root.deiconify()
            if r == "ecran":
                self.cfg["source"] = "ecran"
            elif r:
                self.cfg["region"] = list(r); self.cfg["source"] = "zone"
            save_cfg(self.cfg)
            if "source" in self.vars:
                self.vars["source"].set(self.cfg["source"])
            self._source_changed()
            if then and r:
                then()
        self.root.after(250, lambda: select_region(self.root, done))

    def choose_window(self, then=None):
        def done(res):
            if res:
                self.win_hwnd, title = res
                self.cfg["window_title"] = title[:120]; self.cfg["source"] = "fenetre"; save_cfg(self.cfg)
                if "source" in self.vars:
                    self.vars["source"].set("fenetre")
                self._source_changed()
                if then:
                    then()
        pick_window(self.root, self.pal, done)

    def rec_rect(self):
        """Rectangle a enregistrer (pixels physiques) ou None s'il faut d'abord choisir."""
        s = self.cfg.get("source")
        if s == "zone":
            r = self.cfg.get("region")
            return tuple(r) if r else None
        if s == "fenetre":
            h = self.win_hwnd
            if not (h and IS_WIN and __import__("ctypes").windll.user32.IsWindow(h)):
                from .c02_win32 import find_window
                f = find_window(self.cfg.get("window_title", ""))
                if not f:
                    return None
                h = self.win_hwnd = f[0]
            x, y, w, hh = window_rect(h)
            vx, vy, vw, vh = virtual_screen()
            x0, y0 = max(x, vx), max(y, vy)
            x1, y1 = min(x + w, vx + vw), min(y + hh, vy + vh)
            return (x0, y0, x1 - x0, y1 - y0) if x1 - x0 > 40 and y1 - y0 > 40 else None
        if s == "moniteur":
            ms = monitors(); m = ms[min(int(self.cfg.get("monitor") or 0), len(ms) - 1)]
        else:
            _i, m = monitor_of_point(*cursor_pos())
        return (m["x"], m["y"], m["w"], m["h"])

    def rec_rect_or_screen(self):
        if self.rec is not None:
            return self.rec.rect
        _i, m = monitor_of_point(*cursor_pos())
        return (m["x"], m["y"], m["w"], m["h"])

    def _tool_rect(self):
        """Ecran des outils (dessin, projecteur) : celui de l'enregistrement, sinon celui de la souris."""
        if self.rec is not None:
            x, y, w, h = self.rec.rect
            _i, m = monitor_of_point(x + w // 2, y + h // 2)
        else:
            _i, m = monitor_of_point(*cursor_pos())
        return (m["x"], m["y"], m["w"], m["h"])

    # ---------------------------------------------------------- enregistrer
    def toggle_record(self):
        if self.rec is not None:
            self.stop_recording()
        elif not getattr(self, "_starting", False):
            self.start_recording()

    def start_recording(self):
        rect = self.rec_rect()
        if rect is None:
            if self.cfg.get("source") == "zone":
                return self.choose_region(then=self.start_recording)
            return self.choose_window(then=self.start_recording)
        free = min(free_bytes(self.cfg["out_dir"]), free_bytes(TMP_DIR))  # dossier des videos ET morceaux en cours
        if free < 2 * 1024 ** 3:
            messagebox.showwarning("Espace disque", f"Il reste seulement {human_size(free)} sur le disque.\n"
                                   "Libère de la place (ou choisis un autre dossier) avant d'enregistrer.", parent=self.root)
            return
        self._starting = True
        if self.cfg.get("source") == "fenetre" and self.win_hwnd:
            bring_to_front(self.win_hwnd)
        self.root.withdraw()
        self._cancel_cd = {"stop": False}
        self.root.bind_all("<Escape>", lambda e: self._cancel_cd.update(stop=True))
        n = int(self.cfg.get("countdown") or 0)

        def go():
            self.root.unbind_all("<Escape>")
            if self._cancel_cd.get("stop"):
                self._starting = False; self._restore(); self.status("Enregistrement annulé.")
                self.hotkeys_refresh()
                if self.handoff:
                    self._handoff_cancel()
                return
            threading.Thread(target=self._really_start, args=(rect,), daemon=True).start()
        self.root.after(350, lambda: countdown(self.root, rect, n, go, self._cancel_cd))

    def _really_start(self, rect):
        try:
            cls = Recorder
            if self.cfg.get("source") == "son":
                from .c12_extras import make_audio_recorder
                cls = make_audio_recorder(Recorder)
            rec = cls(self.cfg, rect, log=lambda m: self.root.after(0, self.status, m))
            rec.start()
        except Exception as e:
            logger.exception("demarrage")
            self.root.after(0, self._start_failed, str(e))
            return
        self.root.after(0, self._started, rec)

    def _start_failed(self, msg):
        self._starting = False
        self.hotkeys_refresh()
        self._restore()
        messagebox.showerror("Enregistrement", f"L'enregistrement n'a pas pu démarrer.\n\n{msg}", parent=self.root)
        if self.handoff:
            self._handoff_end(cancelled=True)

    def _started(self, rec):
        self._starting = False
        self.rec = rec
        self.hotkeys_refresh()  # tous les raccourcis pendant l'enregistrement
        self.bar = ControlBar(self, self.cfg.get("hide_bar", True))
        audio_only = self.cfg.get("source") == "son"
        if self.cfg.get("clicks") and not audio_only:
            self.halo.start()
        if self.cfg.get("keys") and not audio_only:
            self.keyb.shortcuts_only = self.cfg.get("keys_shortcuts_only", True)
            self.keyb.start()
        if self.cfg.get("source") in ("zone", "fenetre"):
            self.border = RegionBorder(self.root, rec.rect)
        errs = rec.audio.errors()
        self.status("\u23fa Enregistrement en cours… " + (f"(son : {errs[0]})" if errs else ""))
        self._warned_disk = False
        self.root.after(5000, self._watch_disk)
        if self.handoff:  # venu de l'Archiveur : on retient la fiche (meme en cas de panne → recuperation)
            rec.handoff = dict(self.handoff)
            try:
                rec.man["handoff"] = rec.handoff; rec._save_man()
            except Exception:
                logger.exception("manifeste handoff")
            if self.handoff.get("auto_stop"):
                self.root.after(int(float(self.handoff["auto_stop"]) * 1000),
                                lambda r=rec: self.stop_recording() if self.rec is r else None)
        stop_min = float(getattr(self, "_sched_stop_min", 0) or self.cfg.get("auto_stop_min") or 0)
        self._sched_stop_min = 0
        if stop_min > 0 and not (self.handoff and self.handoff.get("auto_stop")):
            self._auto_stop_at = (rec, stop_min * 60)
            self.root.after(2000, self._watch_auto_stop)
            self.status(f"\u23fa Enregistrement en cours… arrêt automatique après {int(stop_min)} min de vidéo.")

    # ---------------------------------------------------------- arret automatique / programmation / reperes
    def _watch_auto_stop(self):
        rec, limit = getattr(self, "_auto_stop_at", (None, 0))
        if rec is None or self.rec is not rec:
            return
        if rec.elapsed() >= limit:
            self.status("\u23f9 Durée prévue atteinte : on arrête et on sauve.")
            return self.stop_recording()
        self.root.after(1000, self._watch_auto_stop)

    def schedule_recording(self, when, minutes):
        self.cancel_schedule(quiet=True)
        ms = max(0, int((when - __import__("datetime").datetime.now()).total_seconds() * 1000))
        self._sched = (self.root.after(ms, self._sched_fire), when, minutes)
        self.status(f"\u23f0 Enregistrement programmé à {when:%H:%M}" + (f" pendant {minutes} min" if minutes else "") +
                    " — laisse CaptureScreen ouvert.")
        self._sched_label()

    def cancel_schedule(self, quiet=False):
        s = getattr(self, "_sched", None)
        if s:
            try:
                self.root.after_cancel(s[0])
            except Exception:
                pass
        self._sched = None
        self._sched_label()
        if s and not quiet:
            self.status("\u23f0 Programmation annulée.")

    def _sched_label(self):
        s = getattr(self, "_sched", None)
        try:
            self.sched_lab.configure(text=(f"\u23f0 Prévu à {s[1]:%H:%M}" + (f" pendant {s[2]} min" if s[2] else "")) if s else "")
        except Exception:
            pass

    def _sched_fire(self):
        s, self._sched = getattr(self, "_sched", None), None
        self._sched_label()
        if self.rec is not None or getattr(self, "_starting", False):
            return self.status("\u23f0 Heure prévue, mais un enregistrement est déjà en cours.")
        self._sched_stop_min = (s[2] if s else 0)
        old = self.cfg.get("countdown")
        self.cfg["countdown"] = 0
        try:
            self.start_recording()
        finally:
            self.cfg["countdown"] = old

    def hotkey_marker(self):
        if self.rec is None:
            return self.status(f"\U0001f516 Les repères s'ajoutent pendant un enregistrement ({self.hk_label}+K).")
        t = self.rec.add_marker()
        n = len(self.rec.man.get("markers") or [])
        self.marker_flash(f"\U0001f516 Repère {n} · {hms(t)}")

    def marker_prompt(self):
        from .c14_tools_ui import marker_prompt
        marker_prompt(self)

    def marker_flash(self, text):
        """Petite confirmation (invisible dans la video)."""
        try:
            from .c02_win32 import exclude_from_capture
            p = self.pal
            w = tk.Toplevel(self.root); w.overrideredirect(True); w.attributes("-topmost", True)
            tk.Label(w, text=text, bg=p["ACC"], fg=p["ONACC"], font=("Segoe UI", 13, "bold"), padx=14, pady=6).pack()
            exclude_from_capture(w)
            w.update_idletasks()
            w.geometry(f"+{(w.winfo_screenwidth() - w.winfo_reqwidth()) // 2}+{64}")
            w.after(1600, w.destroy)
        except Exception:
            pass

    def _watch_disk(self):
        rec = self.rec
        if rec is None:
            return
        free = min(free_bytes(self.cfg["out_dir"]), free_bytes(TMP_DIR))
        need = int(rec.size() * 1.05) + 1024 ** 3   # le MP4 final a besoin d'environ la meme place
        if free < need:
            self.status("\u26a0 Disque presque plein : l'enregistrement s'arrête proprement.")
            messagebox.showwarning("Disque presque plein", "Le disque est presque plein : j'arrête l'enregistrement "
                                   "maintenant pour qu'il soit sauvé au complet.", parent=self.root)
            self.stop_recording()
            return
        if free < WARN_FREE and not self._warned_disk:
            self._warned_disk = True
            ph = rec.per_hour()
            self.status(f"\u26a0 Il reste {human_size(free)} sur le disque" + (f" (≈ {human_size(ph)} par heure d'enregistrement)" if ph else ""))
        self.root.after(5000, self._watch_disk)

    def toggle_pause(self):
        rec = self.rec
        if rec is None:
            return
        def go():
            try:
                rec.resume() if rec.state == "pause" else rec.pause()
            except Exception as e:
                self.root.after(0, self.status, f"\u26a0 {e}")
            self.root.after(0, self.status, "\u23f8 En pause (rien n'est enregistré)." if rec.state == "pause"
                            else "\u23fa Enregistrement repris.")
        threading.Thread(target=go, daemon=True).start()

    def _end_overlays(self):
        self.halo.stop(); self.keyb.stop()
        for o in (self.bar, self.border):
            if o is not None:
                o.destroy()
        self.bar = self.border = None

    def stop_recording(self):
        rec = self.rec
        if rec is None:
            return
        self.rec = None
        self.hotkeys_refresh()
        self._end_overlays()
        self.status("\U0001f4be On termine la vidéo… (quelques secondes)")
        self._restore()

        handoff = getattr(rec, "handoff", None)

        def go():
            try:
                rec.stop()
                out = rec.finish(self.cfg["out_dir"], video_name(handoff.get("titre")) if handoff else "")
                self.root.after(0, self._saved, out, handoff)
            except Exception as e:
                logger.exception("fin")
                msg = str(e)
                self.root.after(0, lambda: messagebox.showerror(
                    "Enregistrement", f"{msg}\n\nTes morceaux sont gardés : relance CaptureScreen pour les récupérer.",
                    parent=self.root))
        threading.Thread(target=go, daemon=True).start()

    def _saved(self, out, handoff=None):
        if handoff:
            from .c04_recorder import probe_duration
            try:
                dur = round(probe_duration(out), 1)
            except Exception:
                dur = None
            self.handoff_saved(handoff, out, dur)
            try:
                self.lib.refresh(select=out)
            except Exception:
                pass
            self._handoff_end()
            return
        self.status(f"\u2705 Vidéo prête : {os.path.basename(out)}  —  Entrée pour la regarder, \u2702 pour couper le début/la fin.")
        self.lib.refresh(select=out)
        self._celebrate(out)

    def _celebrate(self, out):
        """Ecran « Bravo ! » + notification Windows (desactivables), jamais bloquant."""
        from . import c15_finish as fin
        try:
            if self.cfg.get("notify_done", True) and not os.environ.get("CS_NO_NOTIFY"):
                from .c04_recorder import probe_duration
                d = probe_duration(out)
                fin.notify("\u2705 CaptureScreen : c'est enregistré !",
                           f"{os.path.basename(out)}\n{hms(d)} · {human_size(os.path.getsize(out))}", self._icon_path())
            if self.cfg.get("end_screen", True) and not getattr(self, "_test_mode", False):
                fin.finish_dialog(self, out)
        except Exception:
            logger.exception("ecran de fin")

    def _icon_path(self):
        try:
            import sys as _s
            return os.path.join(os.path.dirname(os.path.abspath(_s.modules["capturescreen_parties"].__file__)), "..",
                                "capturescreen1.ico")
        except Exception:
            return ""

    def cancel_recording(self):
        rec = self.rec
        if rec is None:
            return
        if not messagebox.askyesno("Annuler", "Jeter cet enregistrement ? (il ne sera pas sauvé)", parent=self.root):
            return
        self.rec = None
        self.hotkeys_refresh()
        self._end_overlays()
        threading.Thread(target=rec.discard, daemon=True).start()
        self._restore()
        self.status("Enregistrement jeté.")
        if self.handoff:
            self._handoff_end(cancelled=True)

    def _restore(self):
        if self.handoff:  # demande de l'Archiveur : on reste discret, l'Archiveur reprend la main
            return
        self._restore_normal()

    def _restore_normal(self):
        try:
            self.root.deiconify(); self.root.state("zoomed"); self.root.lift()
        except Exception:
            pass

    # ---------------------------------------------------------- captures d'ecran
    def hotkey_shot(self):
        self.screenshot("ecran" if self.rec is not None else "zone")

    def screenshot_now(self):
        self.screenshot("ecran")

    def screenshot(self, mode):
        rec = self.rec
        was_visible = rec is None and self.root.state() not in ("iconic", "withdrawn")

        def snap(rect):
            def do():
                try:
                    p, ok = screenshot(rect, self.cfg["out_dir"])
                    self.status(f"\U0001f4f7 Image enregistrée : {os.path.basename(p)}" + (" — copiée, colle-la avec Ctrl+V" if ok else ""))
                    self.lib.refresh(select=p)
                except Exception as e:
                    self.status(f"\u26a0 Capture impossible : {e}")
                if was_visible:
                    self._restore()
            self.root.after(250, do)
        if rec is not None:
            return snap(rec.rect)
        if mode == "zone":
            def done(r):
                if r == "ecran":
                    snap(self._tool_rect())
                elif r:
                    snap(r)
                elif was_visible:
                    self._restore()
            if was_visible:
                self.root.withdraw()
            self.root.after(250, lambda: select_region(self.root, done))
        elif mode == "fenetre":
            def picked(res):
                if not res:
                    return
                self.win_hwnd = res[0]
                bring_to_front(res[0])
                self.root.withdraw()
                self.root.after(400, lambda: snap(window_rect(res[0])))
            pick_window(self.root, self.pal, picked)
        else:
            if was_visible:
                self.root.withdraw()
            snap(self._tool_rect())

    # ---------------------------------------------------------- outils a l'ecran
    def toggle_draw(self):
        if self.annot is not None:
            self.annot.toggle_visible(); return
        self.annot = Annotator(self.root, self._tool_rect(), self.pal, tip=self.tip, on_close=self._annot_closed)
        self.status("\u270f Dessin : P crayon · H surligneur · A flèche · R rectangle · T texte · G gomme · Échap = souris libre")

    def toggle_board(self):
        color = self.cfg.get("board_color", "blanc")
        if self.annot is None:
            self.annot = Annotator(self.root, self._tool_rect(), self.pal, board=color, tip=self.tip, on_close=self._annot_closed)
        elif self.annot.board_name:
            self.annot.set_board(None)
        else:
            if not self.annot.visible:
                self.annot.toggle_visible()
            self.annot.set_board(color)

    def _annot_closed(self):
        self.annot = None

    def toggle_spot(self):
        if self.spot is not None and self.spot.active:
            self.spot.stop(); self.spot = None
        else:
            self.spot = Spotlight(self.root, self._tool_rect(), int(self.cfg.get("spot_radius") or 150))
            self.spot.start()

    def toggle_zoom(self):
        self.mag.zoom = float(self.cfg.get("zoom") or 2.0)
        self.mag.toggle()

    def toggle_timer(self):
        self.timer.minutes = int(self.cfg.get("timer_minutes") or 5)
        self.timer.toggle()

    # ---------------------------------------------------------- son
    def test_sound(self):
        self.snd_lab.configure(text="\U0001f442 J'écoute 2 secondes… (fais jouer un son ou parle)")

        def go():
            from .c03_audio import test_levels
            best, errs = test_levels(2.0, self.cfg.get("sys_audio"), self.cfg.get("speaker", ""), self.cfg.get("mic"),
                                     self.cfg.get("mic_name", ""))
            names = {"systeme": "\U0001f50a ordi", "micro": "\U0001f3a4 micro"}
            if not best and not errs:
                txt = "Coche « Son de l'ordi » ou « Micro » d'abord."
            else:
                bits = [f"{names[k]} : {'bon niveau' if v > 0.05 else ('faible' if v > 0.003 else 'silence')}"
                        for k, v in best.items()]
                txt = "  ·  ".join(bits) + ("  ·  \u26a0 " + errs[0] if errs else "")
            self.root.after(0, lambda: self.snd_lab.configure(text=txt))
        threading.Thread(target=go, daemon=True).start()

    # ---------------------------------------------------------- recuperation
    def check_leftovers(self):
        for work, created, dur, size in leftovers():
            when = str(created)[:16].replace("T", " à ")
            r = messagebox.askyesnocancel(
                "Récupérer l'enregistrement",
                f"Un enregistrement du {when} n'a pas été terminé (panne ou fermeture imprévue).\n"
                f"Environ {human_size(size)} ont été sauvés.\n\n"
                "Oui = Récupérer l'enregistrement (en faire une vidéo)\n"
                "Non = Le jeter\n"
                "Annuler = Décider plus tard", parent=self.root)
            if r is None:
                continue
            if r is False:
                shutil.rmtree(work, ignore_errors=True)
                self.status("Enregistrement interrompu jeté.")
                continue
            self.status("\U0001f6df Récupération en cours…")

            def go(w=work):
                try:
                    try:
                        import json as _j
                        with open(os.path.join(w, "session.json"), encoding="utf-8") as fh:
                            ho = _j.load(fh).get("handoff")
                    except Exception:
                        ho = None
                    out = assemble(w, self.cfg["out_dir"], video_name(ho.get("titre")) if ho else "")
                    if ho:  # il venait de l'Archiveur : la video recuperee va quand meme dans sa fiche
                        write_result(ho, out)
                    self.root.after(0, self.status, f"\U0001f6df Récupéré : {os.path.basename(out)}")
                    self.root.after(0, self.lib.refresh, out)
                except Exception as e:
                    logger.exception("recuperation")
                    self.root.after(0, self.status, f"\u26a0 Récupération : {e}")
            threading.Thread(target=go, daemon=True).start()

    # ---------------------------------------------------------- fermeture / aide
    def on_close(self):
        if self.rec is not None:
            r = messagebox.askyesnocancel("Quitter", "Un enregistrement est en cours.\n\nOui = l'arrêter et le sauver, puis quitter\n"
                                          "Non = continuer d'enregistrer", parent=self.root)
            if not r:
                return
            rec = self.rec
            self.rec = None
            self._end_overlays()
            self.status("\U0001f4be On termine la vidéo avant de quitter…")
            self.root.update()
            try:
                rec.stop(); rec.finish(self.cfg["out_dir"])
            except Exception:
                logger.exception("fin a la fermeture")
        for o in (self.spot,):
            if o is not None:
                o.stop()
        self.hk.stop()
        save_cfg(self.cfg)
        self.root.destroy()

    def show_help(self):
        p, hk = self.pal, self.hk_label
        d = tk.Toplevel(self.root); d.title("Aide — CaptureScreen"); d.configure(bg=p["BG"]); d.geometry("820x680")
        d.transient(self.root)
        t = tk.Text(d, wrap="word", bg=p["PANEL"], fg=p["TEXT"], font=("Segoe UI", 11), relief="flat", padx=16, pady=12)
        sb = tk.Scrollbar(d, command=t.yview); t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); t.pack(fill="both", expand=True)
        t.insert("end", f"""\U0001f3a5 CaptureScreen — mode d'emploi

1. Choisis quoi enregistrer : Écran complet, une Fenêtre, une Zone, ou le Son seulement (cours, balado).
2. Coche ce que tu veux : Son de l'ordi, Micro, Webcam, Afficher les touches.
3. Clique sur \u23fa Enregistrer (ou {hk}+R). Un compte à rebours 3-2-1, puis la fenêtre se cache.
4. Une petite barre flottante en haut te montre le temps et la taille. Elle n'apparaît pas dans la vidéo.
5. {hk}+R (ou \u23f9 dans la barre) arrête : la vidéo MP4 apparaît dans « Mes enregistrements ».

RACCOURCIS (marchent partout, même fenêtre cachée)
  Hors enregistrement, seul {hk}+R est pris : {hk}+S, D, B… restent aux autres logiciels
  (Enregistrer sous, favoris…). Réglable dans \u2699 Avancé → Raccourcis (« Aucun » rend aussi
  {hk}+R au navigateur ; F5 et Ctrl+R rechargent toujours la page).
  {hk}+R  Enregistrer / Arrêter          {hk}+P  Pause / Reprendre
  {hk}+S  Capture d'écran (image PNG, aussi copiée : colle avec Ctrl+V)
  {hk}+D  Dessiner à l'écran              {hk}+B  Tableau blanc / noir / vert
  {hk}+L  Projecteur (éclaire la souris)  {hk}+Z  Loupe
  {hk}+M  Minuteur à l'écran              Ctrl+Maj+T  Thème des couleurs
  {hk}+K  Repère (chapitre) à ce moment-ci — le bouton \U0001f516 de la barre permet de lui donner un nom
  F1 aide · F2 renommer · Suppr Corbeille · Entrée ouvrir · F5 actualiser

DESSINER (pendant le dessin)
  P crayon · H surligneur · A flèche · R rectangle · E ellipse (Maj = carré / cercle) · T texte · G gomme
  1 à 6 couleurs · + / − épaisseur · Ctrl+Z annuler · Suppr tout effacer
  Échap ou clic droit = « souris libre » (les traits restent, tu peux cliquer dans tes programmes)

APRÈS L'ENREGISTREMENT
  Un écran « Bravo ! » montre la miniature, la durée, la taille et tes gros boutons : Regarder,
  Dossier, Archiveur, Couper, Outils (désactivable sur l'écran lui-même). Une notification Windows
  prévient aussi quand la vidéo est prête. En haut de la bibliothèque : ton compteur d'heures.

SUR CHAQUE VIGNETTE
  \u25b6 regarder · \U0001f4c2 montrer dans le dossier · \u270f renommer · \u2702 couper le début / la fin
  \U0001f4ac sous-titres automatiques (.srt) · \U0001f4e6 envoyer une copie à l'Archiveur · \U0001f5d1 Corbeille
  \u2139 Résumé : durée, taille, repères cliquables (lire à partir de là), résumé avec chapitres à copier
  \U0001f6e0 Outils : version à partager (720p légère), extrait ou GIF, enlever un passage au milieu,
     joindre plusieurs vidéos, améliorer le son (bruit de fond + volume), garder le son en MP3,
     incruster les sous-titres. Chaque outil crée un nouveau fichier : l'original ne change jamais.

PROGRAMMER (\u2699 Réglages avancés → \u23f0)
  Démarrer tout seul à une heure, arrêter après une durée, ou « arrêter tout seul après 1 h ».

LONGS COURS (2 h et plus)
  La vidéo est sauvée en petits morceaux pendant l'enregistrement. Si le PC plante ou s'éteint,
  rouvre CaptureScreen : il propose « Récupérer l'enregistrement ». Seules les dernières secondes
  peuvent manquer. Si le disque se remplit, l'enregistrement s'arrête tout seul, proprement.
  Si la capture se coupe (pilote graphique, écran qui se met en veille…), elle repart toute seule
  en quelques secondes : la vidéo continue et le Résumé indique les coupures réparées.

BON À SAVOIR
  • La bulle des touches n'écrit jamais rien sur le disque. Avec « Seulement les raccourcis »,
    les lettres que tu tapes (mots de passe) ne s'affichent pas.
  • Certaines vidéos protégées par leur site (Netflix, Tubi, Disney+…) apparaissent en noir : c'est
    Windows qui les protège, CaptureScreen enregistre seulement ce que Windows lui montre.
  • Tes vidéos : {self.cfg['out_dir']}
""")
        t.configure(state="disabled")
        d.bind("<Escape>", lambda e: d.destroy())
