# -*- coding: utf-8 -*-
"""
Gestionnaire de fichiers 5 — port Tkinter local du mode Norton Commander
(GestionnaireFichiers5.php, mode=local).

Panneau gauche = dossiers (+ « .. ») ; panneau droit = fichiers + sous-dossiers.
Clavier NC5: Tab, ↑↓, Home/End, PgUp (upload), PgDn (ouvrir), Enter, Bksp,
Insert (mkdir), Delete/F8, Space (multi-select), Ctrl+C/X/V.
Souris: clic / Ctrl+clic / Shift+clic, double-clic ouvrir, clic droit menu.
Stdlib + tkinter seulement. Pas de FTP/auth web.
Icône fenêtre: gestionnaire_fichiers5.ico/.png (à côté du script).
"""
from __future__ import annotations

import os
import shutil
import sys
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_NAME = "Gestionnaire de fichiers"
APP_FILE_VER = 5  # version fichier seulement — jamais dans le titre UI

# Thème sombre teal / or (proche GF5 : --panel #0d1b2a, accent gold actif)
C = {
    "bg": "#00005a",
    "bg2": "#000080",
    "panel": "#000080",
    "panel2": "#0000aa",
    "panel3": "#000066",
    "line": "#00aaaa",
    "ink": "#ffffff",
    "mut": "#b8d8ff",
    "teal": "#00ffff",
    "accent": "#ffff00",
    "gold": "#ffff00",
    "ok": "#8df0b0",
    "bad": "#ff8d8d",
    "cursor_bg": "#008080",
    "sel_bg": "#0000aa",
    "cursor_sel_bg": "#008080",
    "row": "#000080",
    "row_alt": "#000066",
}


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_ICO = os.path.join(BASE_DIR, "gestionnaire_fichiers5.ico")
ICON_PNG = os.path.join(BASE_DIR, "gestionnaire_fichiers5.png")


def apply_window_icon(root: tk.Misc) -> None:
    """Icône barre de titre / tâche: iconbitmap(.ico) + iconphoto(.png)."""
    kept = []
    try:
        if sys.platform.startswith("win") and os.path.isfile(ICON_ICO):
            root.iconbitmap(default=ICON_ICO)  # type: ignore[attr-defined]
    except Exception:
        try:
            if os.path.isfile(ICON_ICO):
                root.iconbitmap(ICON_ICO)  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        if os.path.isfile(ICON_PNG):
            img = tk.PhotoImage(file=ICON_PNG)
            root.iconphoto(True, img)
            kept.append(img)
    except Exception:
        pass
    # garder une ref pour éviter le GC de PhotoImage
    root._app_icons = kept  # type: ignore[attr-defined]


LEFT, RIGHT = "left", "right"
Entry = Tuple[str, str, bool]  # name, fullpath, is_dir


def human_size(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        return "—"
    if n < 1024:
        return f"{n} o"
    for unit in ("Ko", "Mo", "Go", "To"):
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} Po"


def fmt_mtime(path: str) -> str:
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"


def default_root() -> str:
    if sys.platform.startswith("win"):
        for cand in ("C:\\", os.path.expanduser("~")):
            if cand and os.path.isdir(cand):
                return os.path.abspath(cand)
    home = os.path.expanduser("~")
    if home and os.path.isdir(home):
        return home
    return os.path.abspath(os.sep)


def open_local(path: str) -> None:
    """Équivalent download/open local (os.startfile / xdg-open / open)."""
    if not path or not os.path.exists(path):
        raise FileNotFoundError(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", path])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", path])


class FileManagerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x720")
        self.minsize(800, 480)
        self.configure(bg=C["bg"])
        apply_window_icon(self)
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.cwd = default_root()
        self.active_pane = RIGHT
        self.left_idx = 0
        self.right_idx = 0
        self.left_items: List[Entry] = []
        self.right_items: List[Entry] = []
        self.left_selected: Set[str] = set()
        self.right_selected: Set[str] = set()
        # clipboard interne cut: list of (src_path, is_dir)
        self.clipboard_cut: Optional[List[Tuple[str, bool]]] = None
        self.clipboard_copy: Optional[List[Tuple[str, bool]]] = None
        self._painting = False
        self._filter = ""
        self._shift_anchor = {LEFT: None, RIGHT: None}  # index ancre Shift+clic

        self._build_ui()
        self._bind_keys()
        self.refresh()
        self.after(80, self._focus_active)

    # ── UI ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "GF.TButton",
            background=C["panel2"],
            foreground=C["ink"],
            bordercolor=C["line"],
            focusthickness=1,
            padding=(8, 4),
            font=("Consolas", 10, "bold"),
        )
        style.map(
            "GF.TButton",
            background=[("active", C["panel3"]), ("pressed", C["line"])],
            foreground=[("active", C["accent"])],
        )
        style.configure(
            "GF.TEntry",
            fieldbackground=C["panel3"],
            foreground=C["ink"],
            insertcolor=C["ink"],
            bordercolor=C["line"],
        )

        # Barre chemin
        top = tk.Frame(self, bg=C["bg2"], padx=8, pady=6)
        top.pack(fill=tk.X)
        # Icône dossier cliquable : ouvre le sélecteur et navigue vers le dossier choisi.
        try:
            self._folder_button_image = tk.PhotoImage(file=ICON_PNG)
            self.folder_button = tk.Label(
                top,
                image=self._folder_button_image,
                bg=C["bg2"],
                cursor="hand2",
                padx=2,
                pady=1,
            )
        except Exception:
            self._folder_button_image = None
            self.folder_button = tk.Label(
                top, text="[Dossier]", bg=C["bg2"], fg=C["teal"],
                font=("Consolas", 10, "bold"), cursor="hand2",
            )
        self.folder_button.pack(side=tk.LEFT)
        self.folder_button.bind("<Button-1>", self.choose_directory)
        self.folder_button.bind("<Enter>", self._folder_tooltip_enter)
        self.folder_button.bind("<Leave>", self._folder_tooltip_leave)
        self.path_var = tk.StringVar(value=self.cwd)
        self.path_entry = tk.Entry(
            top,
            textvariable=self.path_var,
            bg=C["panel3"],
            fg=C["ink"],
            insertbackground=C["ink"],
            relief=tk.FLAT,
            font=("Consolas", 10),
            highlightthickness=1,
            highlightbackground=C["line"],
            highlightcolor=C["teal"],
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        self.path_entry.bind("<Return>", self._on_path_enter)
        ttk.Button(top, text="Aller", style="GF.TButton", command=self._on_path_enter).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(top, text="⬆ Parent", style="GF.TButton", command=self.go_parent).pack(
            side=tk.LEFT, padx=2
        )

        # Toolbar actions
        bar = tk.Frame(self, bg=C["panel2"], padx=6, pady=4)
        bar.pack(fill=tk.X)
        for label, cmd in (
            ("➕ Insert", self.mkdir_dialog),
            ("🗑 Delete", self.delete_selected),
            ("↻ F5 Rafraîchir", self.refresh),
            ("✏ Renommer", self.rename_selected),
            ("✂ Couper", self.cut_selected),
                        ("Copier", self.copy_selected),
("📋 Coller", self.paste_clipboard),
        ):
            ttk.Button(bar, text=label, style="GF.TButton", command=cmd).pack(
                side=tk.LEFT, padx=2
            )
        ttk.Button(bar, text="Upload (PageUp)", style="GF.TButton", command=self.upload_files).pack(
            side=tk.LEFT, padx=2
        )
        tk.Label(bar, text="Filtre:", bg=C["panel2"], fg=C["mut"], font=("Consolas", 10)).pack(
            side=tk.LEFT, padx=(12, 4)
        )
        self.filter_var = tk.StringVar()
        self.filter_entry = tk.Entry(
            bar,
            textvariable=self.filter_var,
            width=22,
            bg=C["panel3"],
            fg=C["ink"],
            insertbackground=C["ink"],
            relief=tk.FLAT,
            font=("Consolas", 10),
            highlightthickness=1,
            highlightbackground=C["line"],
            highlightcolor=C["teal"],
        )
        self.filter_entry.pack(side=tk.LEFT)
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())

        # Panneaux
        mid = tk.Frame(self, bg=C["bg"], padx=6, pady=4)
        mid.pack(fill=tk.BOTH, expand=True)

        self.left_frame = tk.Frame(
            mid,
            bg=C["panel"],
            highlightthickness=2,
            highlightbackground=C["line"],
            highlightcolor=C["gold"],
        )
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        self.right_frame = tk.Frame(
            mid,
            bg=C["panel"],
            highlightthickness=2,
            highlightbackground=C["line"],
            highlightcolor=C["gold"],
        )
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))

        self.left_title = tk.Label(
            self.left_frame,
            text="📁 Dossiers",
            bg=C["panel2"],
            fg=C["teal"],
            font=("Consolas", 12, "bold"),
            anchor="w",
            padx=8,
            pady=4,
        )
        self.left_title.pack(fill=tk.X)
        self.right_title = tk.Label(
            self.right_frame,
            text="📄 Fichiers",
            bg=C["panel2"],
            fg=C["teal"],
            font=("Consolas", 12, "bold"),
            anchor="w",
            padx=8,
            pady=4,
        )
        self.right_title.pack(fill=tk.X)

        self.left_list = self._make_listbox(self.left_frame)
        self.right_list = self._make_listbox(self.right_frame)

        self.left_list.bind("<Button-1>", lambda e: self._on_click(LEFT, e))
        self.right_list.bind("<Button-1>", lambda e: self._on_click(RIGHT, e))
        self.left_list.bind("<Double-Button-1>", lambda e: self._on_double(LEFT, e))
        self.right_list.bind("<Double-Button-1>", lambda e: self._on_double(RIGHT, e))
        self.left_list.bind("<Button-3>", lambda e: self._on_right_click(LEFT, e))
        self.right_list.bind("<Button-3>", lambda e: self._on_right_click(RIGHT, e))
        self.left_list.bind("<FocusIn>", lambda e: self.set_active(LEFT, announce=False))
        self.right_list.bind("<FocusIn>", lambda e: self.set_active(RIGHT, announce=False))

        # Status / hints NC5
        hints = (
            "Tab panneau  ·  ↑↓ curseur  ·  Home/End  ·  PgUp upload / Ctrl+PgUp page  ·  "
            "PgDn/Enter ouvrir  ·  Bksp parent  ·  Insert mkdir  ·  Space multi-select  ·  "
            "Clic / Ctrl+clic / Shift+clic  ·  Clic droit menu  ·  "
            "Delete/F8  |  Ctrl+C/X/V"
        )
        self.status = tk.Label(
            self,
            text=hints,
            bg="#000000",
            fg="#ffe696",
            font=("Consolas", 10),
            anchor="w",
            padx=8,
            pady=4,
            relief=tk.FLAT,
        )
        self.status.pack(fill=tk.X, side=tk.BOTTOM)
        self.msg = tk.Label(
            self,
            text="Prêt.",
            bg=C["bg2"],
            fg=C["mut"],
            font=("Consolas", 10),
            anchor="w",
            padx=8,
            pady=2,
        )
        self.msg.pack(fill=tk.X, side=tk.BOTTOM)

        self._paint_active_border()

    def _make_listbox(self, parent: tk.Frame) -> tk.Listbox:
        wrap = tk.Frame(parent, bg=C["panel"])
        wrap.pack(fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(wrap, orient=tk.VERTICAL)
        lb = tk.Listbox(
            wrap,
            bg=C["panel"],
            fg=C["ink"],
            selectmode=tk.EXTENDED,
            activestyle="none",
            exportselection=False,
            font=("Consolas", 10),
            highlightthickness=0,
            relief=tk.FLAT,
            borderwidth=0,
            yscrollcommand=sb.set,
            selectbackground=C["sel_bg"],
            selectforeground=C["ink"],
        )
        sb.config(command=lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return lb

    def _bind_keys(self) -> None:
        self.bind("<Tab>", self._on_tab)
        self.bind("<ISO_Left_Tab>", self._on_tab)
        self.bind("<Up>", lambda e: self._move(-1))
        self.bind("<Down>", lambda e: self._move(1))
        self.bind("<Home>", lambda e: self._jump("home"))
        self.bind("<End>", lambda e: self._jump("end"))
        self.bind("<Prior>", lambda e: self.upload_files())  # PageUp = upload
        self.bind("<Control-Prior>", lambda e: self._page(-1))  # Ctrl+PageUp = page
        self.bind("<Next>", lambda e: self._page_down_open())  # PageDown = open
        self.bind("<Return>", lambda e: self._open_cursor())
        self.bind("<BackSpace>", lambda e: self.go_parent())
        self.bind("<Insert>", lambda e: self.mkdir_dialog())
        self.bind("<Delete>", lambda e: self.delete_selected())
        self.bind("<F8>", lambda e: self.delete_selected())
        self.bind("<F5>", lambda e: self.refresh())
        self.bind("<space>", lambda e: self._toggle_select())
        self.bind("<F2>", lambda e: self.rename_selected())
        self.bind_all("<Control-c>", self.copy_selected)
        self.bind_all("<Control-x>", self.cut_selected)
        self.bind_all("<Control-v>", self.paste_clipboard)
        # Empêcher Tab de sortir du focus app
        self.bind_all("<Tab>", self._on_tab)

    def _focus_active(self) -> None:
        lb = self.left_list if self.active_pane == LEFT else self.right_list
        try:
            lb.focus_set()
        except Exception:
            pass

    # ── messages / status ───────────────────────────────────────────
    def say(self, text: str) -> None:
        self.msg.configure(text=text, fg=C["teal"])
        self.after(4000, lambda: self.msg.configure(fg=C["mut"]))

    # ── navigation / listing ────────────────────────────────────────
    def _folder_tooltip_enter(self, event=None):
        """Affiche une aide française au survol de l'icône dossier."""
        self._folder_tooltip_leave()
        tip = tk.Toplevel(self)
        tip.wm_overrideredirect(True)
        tip.configure(bg="#ffffe1")
        label = tk.Label(
            tip,
            text="Parcourir les dossiers (choisir un répertoire)",
            bg="#ffffe1",
            fg="#000000",
            relief=tk.SOLID,
            borderwidth=1,
            padx=5,
            pady=2,
            font=("Segoe UI", 9),
        )
        label.pack()
        tip.update_idletasks()
        x = self.folder_button.winfo_rootx()
        y = self.folder_button.winfo_rooty() + self.folder_button.winfo_height() + 3
        tip.geometry(f"+{x}+{y}")
        self._folder_tooltip = tip

    def _folder_tooltip_leave(self, event=None):
        tip = getattr(self, "_folder_tooltip", None)
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass
            self._folder_tooltip = None

    def choose_directory(self, event=None):
        """Choisit un dossier, puis met à jour le chemin et les panneaux."""
        target = filedialog.askdirectory(
            parent=self,
            title="Choisir un dossier",
            initialdir=self.cwd,
            mustexist=True,
        )
        if target:
            self.set_cwd(target)
            self.say(f"Dossier choisi : {self.cwd}")
        return "break"
    def set_cwd(self, path: str) -> None:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            self.say(f"Dossier invalide: {path}")
            return
        self.cwd = path
        self.path_var.set(self.cwd)
        self.left_selected.clear()
        self.right_selected.clear()
        self.left_idx = 0
        self.right_idx = 0
        self.refresh()

    def go_parent(self, event=None):
        parent = os.path.dirname(self.cwd.rstrip("\\/"))
        if not parent or parent == self.cwd:
            # Windows: remonter vers racine disque, ou rester
            drive, tail = os.path.splitdrive(self.cwd)
            if sys.platform.startswith("win") and drive and (tail in ("\\", "/", "")):
                self.say("🏠 Déjà à la racine du lecteur.")
                return "break"
            if self.cwd in (os.sep, "/"):
                self.say("🏠 Déjà à la racine.")
                return "break"
        if parent and os.path.isdir(parent):
            self.active_pane = LEFT
            self.set_cwd(parent)
            self.say(f"⬆ Parent → {self.cwd}")
        else:
            self.say("Parent indisponible.")
        return "break"

    def _on_path_enter(self, event=None):
        target = self.path_var.get().strip().strip('"')
        if target:
            self.set_cwd(target)
        return "break"

    def _list_dir(self) -> Tuple[List[Entry], List[Entry]]:
        """Retourne (left_dirs_with_parent, right_files_and_dirs)."""
        dirs: List[Entry] = []
        files: List[Entry] = []
        try:
            names = os.listdir(self.cwd)
        except PermissionError:
            self.say(f"🔒 Accès refusé: {self.cwd}")
            names = []
        except Exception as e:
            self.say(f"Erreur lecture: {e}")
            names = []

        parent = os.path.dirname(self.cwd.rstrip("\\/"))
        can_parent = bool(parent) and parent != self.cwd and os.path.isdir(parent)
        if sys.platform.startswith("win"):
            drive, tail = os.path.splitdrive(self.cwd)
            if drive and tail not in ("\\", "/", ""):
                can_parent = True
            elif drive and tail in ("\\", "/", ""):
                can_parent = False

        left: List[Entry] = []
        if can_parent or True:
            # Toujours offrir « .. » si un parent existe
            p = os.path.dirname(os.path.abspath(self.cwd))
            if p and p != os.path.abspath(self.cwd):
                left.append(("..", p, True))
            elif sys.platform.startswith("win"):
                # racine lecteur: pas de ..
                pass
            else:
                if self.cwd != os.sep:
                    left.append(("..", p or os.sep, True))

        filt = (self._filter or "").lower().strip()

        for name in names:
            if name in (".", ".."):
                continue
            full = os.path.join(self.cwd, name)
            try:
                is_dir = os.path.isdir(full)
            except Exception:
                continue
            if filt and filt not in name.lower():
                continue
            if is_dir:
                dirs.append((name, full, True))
            else:
                files.append((name, full, False))

        dirs.sort(key=lambda x: x[0].lower())
        files.sort(key=lambda x: x[0].lower())
        left.extend(dirs)
        right = dirs + files
        return left, right

    def refresh(self, event=None):
        self._filter = self.filter_var.get()
        self.left_items, self.right_items = self._list_dir()
        self._fill_list(self.left_list, self.left_items, LEFT)
        self._fill_list(self.right_list, self.right_items, RIGHT)
        self._clamp_indices()
        self._paint_cursors()
        self.path_var.set(self.cwd)
        n_d = sum(1 for x in self.right_items if x[2])
        n_f = sum(1 for x in self.right_items if not x[2])
        self.say(f"↻ {self.cwd}  —  {n_d} dossier(s), {n_f} fichier(s)")
        return "break"

    def _apply_filter(self) -> None:
        self._filter = self.filter_var.get()
        self.left_items, self.right_items = self._list_dir()
        self._fill_list(self.left_list, self.left_items, LEFT)
        self._fill_list(self.right_list, self.right_items, RIGHT)
        self._clamp_indices()
        self._paint_cursors()

    def _fill_list(self, lb: tk.Listbox, items: List[Entry], pane: str) -> None:
        self._painting = True
        lb.delete(0, tk.END)
        selected = self.left_selected if pane == LEFT else self.right_selected
        for i, (name, full, is_dir) in enumerate(items):
            if name == "..":
                label = "⬆ ..  (dossier parent)"
            elif is_dir:
                stamp = fmt_mtime(full)
                label = f"📁 {name}    {stamp}"
            else:
                try:
                    sz = os.path.getsize(full)
                except Exception:
                    sz = 0
                label = f"📄 {name}    {human_size(sz)} · {fmt_mtime(full)}"
            lb.insert(tk.END, label)
            if full in selected or (name == ".." and ".." in selected):
                lb.selection_set(i)
            bg = C["row_alt"] if i % 2 else C["row"]
            lb.itemconfig(i, bg=bg, fg=C["ink"])
        self._painting = False

    def _clamp_indices(self) -> None:
        if self.left_items:
            self.left_idx = max(0, min(self.left_idx, len(self.left_items) - 1))
        else:
            self.left_idx = 0
        if self.right_items:
            self.right_idx = max(0, min(self.right_idx, len(self.right_items) - 1))
        else:
            self.right_idx = 0

    # ── active pane / cursor paint ──────────────────────────────────
    def set_active(self, pane: str, announce: bool = True) -> None:
        self.active_pane = LEFT if pane == LEFT else RIGHT
        self._paint_active_border()
        self._paint_cursors()
        self._focus_active()
        if announce:
            self.say(
                "📁 Panneau dossiers (actif)"
                if self.active_pane == LEFT
                else "📄 Panneau fichiers (actif)"
            )

    def _paint_active_border(self) -> None:
        if self.active_pane == LEFT:
            self.left_frame.configure(highlightbackground=C["gold"], highlightcolor=C["gold"])
            self.right_frame.configure(highlightbackground=C["line"], highlightcolor=C["line"])
            self.left_title.configure(fg=C["accent"])
            self.right_title.configure(fg=C["teal"])
        else:
            self.right_frame.configure(highlightbackground=C["gold"], highlightcolor=C["gold"])
            self.left_frame.configure(highlightbackground=C["line"], highlightcolor=C["line"])
            self.right_title.configure(fg=C["accent"])
            self.left_title.configure(fg=C["teal"])

    def _paint_cursors(self) -> None:
        self._paint_one(self.left_list, self.left_items, self.left_idx, self.left_selected, LEFT)
        self._paint_one(self.right_list, self.right_items, self.right_idx, self.right_selected, RIGHT)

    def _paint_one(
        self,
        lb: tk.Listbox,
        items: List[Entry],
        idx: int,
        selected: Set[str],
        pane: str,
    ) -> None:
        n = lb.size()
        for i in range(n):
            if i >= len(items):
                break
            name, full, _ = items[i]
            key = full if name != ".." else ".."
            is_sel = key in selected or full in selected
            is_cur = (pane == self.active_pane) and (i == idx)
            if is_cur and is_sel:
                bg, fg = C["cursor_sel_bg"], C["gold"]
            elif is_cur:
                bg, fg = C["cursor_bg"], C["gold"]
            elif is_sel:
                bg, fg = C["sel_bg"], C["teal"]
            else:
                bg = C["row_alt"] if i % 2 else C["row"]
                fg = C["ink"]
            try:
                lb.itemconfig(i, bg=bg, fg=fg)
            except Exception:
                pass
        if items and 0 <= idx < n:
            try:
                lb.see(idx)
            except Exception:
                pass

    # ── keyboard handlers ───────────────────────────────────────────
    def _on_tab(self, event=None):
        # Ne pas voler Tab dans les Entry (chemin / filtre)
        w = self.focus_get()
        if isinstance(w, (tk.Entry, ttk.Entry)):
            return None
        self.set_active(RIGHT if self.active_pane == LEFT else LEFT, announce=True)
        return "break"

    def _items_idx(self) -> Tuple[List[Entry], int]:
        if self.active_pane == LEFT:
            return self.left_items, self.left_idx
        return self.right_items, self.right_idx

    def _set_idx(self, idx: int) -> None:
        items, _ = self._items_idx()
        if not items:
            return
        idx = max(0, min(len(items) - 1, idx))
        if self.active_pane == LEFT:
            self.left_idx = idx
        else:
            self.right_idx = idx
        self._paint_cursors()

    def _move(self, delta: int, event=None):
        if self._typing():
            return None
        items, idx = self._items_idx()
        if not items:
            return "break"
        self._set_idx(idx + delta)
        return "break"

    def _jump(self, where: str, event=None):
        if self._typing():
            return None
        items, _ = self._items_idx()
        if not items:
            return "break"
        self._set_idx(0 if where == "home" else len(items) - 1)
        return "break"

    def _page_size(self) -> int:
        lb = self.left_list if self.active_pane == LEFT else self.right_list
        try:
            h = lb.winfo_height()
            # approx row height
            return max(1, (h // 22) - 1)
        except Exception:
            return 10

    def _page(self, direction: int, event=None):
        if self._typing():
            return None
        self._move(direction * self._page_size())
        return "break"

    def upload_files(self, event=None):
        """PageUp = choisir et copier des fichiers dans le dossier courant."""
        if self._typing():
            return None
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Uploader des fichiers",
            initialdir=self.cwd,
        )
        if not paths:
            self.say("PageUp - aucun fichier choisi")
            return "break"
        copied, failed, skipped = 0, 0, 0
        for src in paths:
            name = os.path.basename(src)
            dest = os.path.join(self.cwd, name)
            if os.path.abspath(src) == os.path.abspath(dest):
                skipped += 1
                continue
            try:
                shutil.copy2(src, dest)
                copied += 1
            except Exception as e:
                failed += 1
                self.say(f"PageUp - échec {name}: {e}")
        self.refresh()
        self.say(
            f"PageUp - uploadé {copied} fichier(s) dans le dossier courant"
            f" (échecs {failed}, ignorés {skipped})"
        )
        return "break"

    def _page_down_open(self, event=None):
        """PageDown = ouvrir/télécharger local (os.startfile) le focus fichier."""
        if self._typing():
            return None
        self.active_pane = RIGHT
        self._paint_active_border()
        items, idx = self.right_items, self.right_idx
        if not items:
            self.say("PageDown — rien à ouvrir")
            return "break"
        name, full, is_dir = items[max(0, min(len(items) - 1, idx))]
        if is_dir:
            self.set_cwd(full)
            self.say(f"PageDown — dossier {name}")
        else:
            try:
                open_local(full)
                self.say(f"PageDown — ouvert {name}")
            except Exception as e:
                self.say(f"PageDown — erreur: {e}")
        return "break"

    def _typing(self) -> bool:
        w = self.focus_get()
        return isinstance(w, (tk.Entry, ttk.Entry))

    def _toggle_select(self, event=None):
        if self._typing():
            return None
        items, idx = self._items_idx()
        if not items:
            return "break"
        name, full, _ = items[max(0, min(len(items) - 1, idx))]
        if name == "..":
            self.say("Space — pas sur dossier parent")
            return "break"
        selected = self.left_selected if self.active_pane == LEFT else self.right_selected
        if full in selected:
            selected.discard(full)
            self.say("Space — désélectionné")
        else:
            selected.add(full)
            self.say("Space — sélectionné (+)")
        self._paint_cursors()
        return "break"

    def _cursor_entry(self) -> Optional[Entry]:
        items, idx = self._items_idx()
        if not items:
            return None
        return items[max(0, min(len(items) - 1, idx))]

    def _open_cursor(self, event=None):
        if self._typing():
            return None
        ent = self._cursor_entry()
        if not ent:
            return "break"
        name, full, is_dir = ent
        if is_dir:
            self.set_cwd(full)
            self.say(f"Enter — {name}")
        else:
            try:
                open_local(full)
                self.say(f"Enter — ouvert {name}")
            except Exception as e:
                messagebox.showerror(APP_NAME, f"Impossible d'ouvrir:\n{full}\n\n{e}")
        return "break"

    def _pane_state(self, pane: str):
        if pane == LEFT:
            return self.left_list, self.left_items, self.left_selected
        return self.right_list, self.right_items, self.right_selected

    def _set_pane_idx(self, pane: str, idx: int) -> None:
        if pane == LEFT:
            self.left_idx = idx
        else:
            self.right_idx = idx

    def _sync_listbox_selection(self, pane: str) -> None:
        lb, items, selected = self._pane_state(pane)
        try:
            lb.selection_clear(0, tk.END)
            for i, (name, full, _) in enumerate(items):
                key = full if name != ".." else ".."
                if key in selected or full in selected:
                    lb.selection_set(i)
        except Exception:
            pass

    def _on_click(self, pane: str, event):
        """Clic: select · Ctrl+clic: toggle · Shift+clic: plage."""
        self.set_active(pane, announce=False)
        lb, items, selected = self._pane_state(pane)
        if not items:
            return "break"
        idx = lb.nearest(event.y)
        if idx < 0 or idx >= len(items):
            return "break"
        self._set_pane_idx(pane, idx)
        name, full, _is_dir = items[idx]
        ctrl = bool(event.state & 0x4)
        shift = bool(event.state & 0x1)

        if shift and self._shift_anchor.get(pane) is not None:
            anchor = int(self._shift_anchor[pane])
            lo, hi = (anchor, idx) if anchor <= idx else (idx, anchor)
            if not ctrl:
                selected.clear()
            count = 0
            for i in range(lo, hi + 1):
                n, f, _ = items[i]
                if n == "..":
                    continue
                selected.add(f)
                count += 1
            self.say(f"Shift+clic — plage {count} élément(s)")
        elif ctrl:
            if name == "..":
                self.say("Ctrl+clic — pas sur dossier parent")
            elif full in selected:
                selected.discard(full)
                self.say(f"Ctrl+clic — désélectionné · {name}")
            else:
                selected.add(full)
                self.say(f"Ctrl+clic — ajouté · {name}")
            self._shift_anchor[pane] = idx
        else:
            selected.clear()
            if name != "..":
                selected.add(full)
                self.say(f"Sélectionné · {name}")
            else:
                self.say("Curseur · .. (dossier parent)")
            self._shift_anchor[pane] = idx

        self._sync_listbox_selection(pane)
        self._paint_cursors()
        return "break"

    def _on_double(self, pane: str, event):
        self.set_active(pane, announce=False)
        lb, items, _selected = self._pane_state(pane)
        if not items:
            return "break"
        idx = lb.nearest(event.y)
        if 0 <= idx < len(items):
            self._set_pane_idx(pane, idx)
            self._paint_cursors()
            self._open_cursor()
        return "break"

    def _on_right_click(self, pane: str, event):
        """Clic droit: sélectionne l'item si besoin, puis menu contextuel FR."""
        self.set_active(pane, announce=False)
        lb, items, selected = self._pane_state(pane)
        if items:
            idx = lb.nearest(event.y)
            if 0 <= idx < len(items):
                self._set_pane_idx(pane, idx)
                name, full, _ = items[idx]
                if name != ".." and full not in selected:
                    selected.clear()
                    selected.add(full)
                    self._shift_anchor[pane] = idx
                self._sync_listbox_selection(pane)
                self._paint_cursors()
        self._show_context_menu(pane, event)
        return "break"

    def _show_context_menu(self, pane: str, event) -> None:
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=C["panel2"],
            fg=C["ink"],
            activebackground=C["cursor_bg"],
            activeforeground=C["gold"],
            font=("Consolas", 10),
        )
        menu.add_command(label="Ouvrir", command=self._open_cursor)
        menu.add_separator()
        menu.add_command(label="Copier\tCtrl+C", command=self.copy_selected)
        menu.add_command(label="Couper\tCtrl+X", command=self.cut_selected)
        menu.add_command(label="Coller\tCtrl+V", command=self.paste_clipboard)
        menu.add_separator()
        menu.add_command(label="Renommer\tF2", command=self.rename_selected)
        menu.add_command(label="Supprimer\tDel", command=self.delete_selected)
        menu.add_command(label="Upload\tPgUp", command=self.upload_files)
        menu.add_separator()
        menu.add_command(label="Nouveau dossier\tInsert", command=self.mkdir_dialog)
        menu.add_command(label="Rafraîchir\tF5", command=self.refresh)
        menu.add_separator()
        menu.add_command(label="Propriétés / chemin", command=self.show_properties)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_properties(self, event=None):
        sels = self._selection_paths()
        if not sels:
            ent = self._cursor_entry()
            if not ent or ent[0] == "..":
                self.say("Propriétés — aucune sélection")
                return "break"
            sels = [ent]
        lines = []
        for name, full, is_dir in sels[:15]:
            kind = "Dossier" if is_dir else "Fichier"
            try:
                sz = "—" if is_dir else human_size(os.path.getsize(full))
            except Exception:
                sz = "?"
            lines.append(
                f"{kind}: {name}\n  Chemin: {full}\n  Taille: {sz}\n  Modifié: {fmt_mtime(full)}"
            )
        if len(sels) > 15:
            lines.append(f"… et {len(sels) - 15} autre(s)")
        messagebox.showinfo(APP_NAME, "\n\n".join(lines))
        return "break"


    # ── actions ─────────────────────────────────────────────────────
    def mkdir_dialog(self, event=None):
        if self._typing() and event is not None:
            # Insert depuis entry: laisser passer? Non, on ignore si filtre focus
            pass
        name = simpledialog.askstring(
            "Insert · Nouveau répertoire",
            "Nom du répertoire:",
            parent=self,
        )
        if name is None:
            return "break"
        name = name.strip()
        if not name:
            self.say("Insert · Nom de répertoire vide")
            return "break"
        if any(ch in name for ch in ("/", "\\", "\0")):
            messagebox.showerror(APP_NAME, "Nom invalide (pas de / ou \\).")
            return "break"
        if not messagebox.askyesno(
            APP_NAME, f"Insert · Créer le répertoire « {name} » ?"
        ):
            return "break"
        target = os.path.join(self.cwd, name)
        try:
            os.mkdir(target)
            self.say(f"Insert · Créé « {name} »")
            self.refresh()
            # focus le nouveau
            for i, (n, f, d) in enumerate(self.right_items):
                if f == target:
                    self.active_pane = RIGHT
                    self.right_idx = i
                    self._paint_active_border()
                    self._paint_cursors()
                    break
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Création impossible:\n{e}")
        return "break"

    def _selection_paths(self, pane: Optional[str] = None) -> List[Entry]:
        pane = pane or self.active_pane
        items = self.left_items if pane == LEFT else self.right_items
        selected = self.left_selected if pane == LEFT else self.right_selected
        out: List[Entry] = []
        for name, full, is_dir in items:
            if name == "..":
                continue
            if full in selected:
                out.append((name, full, is_dir))
        if not out:
            # fallback: curseur
            idx = self.left_idx if pane == LEFT else self.right_idx
            if items and 0 <= idx < len(items):
                name, full, is_dir = items[idx]
                if name != "..":
                    out.append((name, full, is_dir))
        return out

    def delete_selected(self, event=None):
        if self._typing() and event is not None:
            return None
        if self.active_pane == LEFT:
            return self._delete_left_folder()
        sels = self._selection_paths(RIGHT)
        if not sels:
            self.say("Delete — aucune sélection")
            return "break"
        names = ", ".join(s[0] for s in sels[:8]) + ("…" if len(sels) > 8 else "")
        if not messagebox.askyesno(
            APP_NAME, f"Delete — Supprimer {len(sels)} élément(s) ?\n{names}"
        ):
            return "break"
        ok, fail = 0, 0
        for name, full, is_dir in sels:
            try:
                if is_dir:
                    if os.listdir(full):
                        if not messagebox.askyesno(
                            APP_NAME,
                            f"« {name} » n'est pas vide.\nSupprimer récursivement ?",
                        ):
                            fail += 1
                            continue
                        shutil.rmtree(full)
                    else:
                        os.rmdir(full)
                else:
                    os.remove(full)
                ok += 1
                self.right_selected.discard(full)
                self.left_selected.discard(full)
            except Exception as e:
                fail += 1
                self.say(f"Échec {name}: {e}")
        self.refresh()
        self.say(f"Delete — ok {ok}, échec {fail}")
        return "break"

    def _delete_left_folder(self):
        items = self.left_items
        if not items:
            self.say("Delete — aucun dossier")
            return "break"
        name, full, is_dir = items[max(0, min(len(items) - 1, self.left_idx))]
        if name == "..":
            self.say("Delete — choisis un répertoire (pas parent)")
            return "break"
        try:
            content = os.listdir(full)
        except Exception as e:
            if not messagebox.askyesno(
                APP_NAME,
                f"Impossible de lister « {name} » ({e}).\nSupprimer récursivement quand même ?",
            ):
                return "break"
            try:
                shutil.rmtree(full)
                self.say(f"Delete — « {name} » supprimé")
                self.refresh()
            except Exception as e2:
                messagebox.showerror(APP_NAME, str(e2))
            return "break"
        if not content:
            if not messagebox.askyesno(
                APP_NAME, f"Delete — Supprimer le répertoire vide « {name} » ?"
            ):
                return "break"
            try:
                os.rmdir(full)
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                return "break"
        else:
            n_d = sum(1 for x in content if os.path.isdir(os.path.join(full, x)))
            n_f = len(content) - n_d
            if not messagebox.askyesno(
                APP_NAME,
                f"Delete — « {name} » contient {n_f} fichier(s)/{n_d} dossier(s) "
                f"(total {len(content)}), supprimer quand même ?\n"
                "Suppression récursive.",
            ):
                return "break"
            try:
                shutil.rmtree(full)
            except Exception as e:
                messagebox.showerror(APP_NAME, str(e))
                return "break"
        self.left_selected.discard(full)
        self.refresh()
        self.say(f"Delete — « {name} » supprimé")
        return "break"

    def rename_selected(self, event=None):
        sels = self._selection_paths()
        if not sels:
            self.say("Renommer — rien de sélectionné")
            return "break"
        if len(sels) > 1:
            self.say("Renommer — un seul élément à la fois")
            return "break"
        name, full, _ = sels[0]
        new = simpledialog.askstring(
            "Renommer", f"Nouveau nom pour « {name} »:", initialvalue=name, parent=self
        )
        if new is None:
            return "break"
        new = new.strip()
        if not new or new == name:
            return "break"
        if any(ch in new for ch in ("/", "\\", "\0")):
            messagebox.showerror(APP_NAME, "Nom invalide.")
            return "break"
        dest = os.path.join(os.path.dirname(full), new)
        if os.path.exists(dest):
            messagebox.showerror(APP_NAME, f"« {new} » existe déjà.")
            return "break"
        try:
            os.rename(full, dest)
            self.left_selected.discard(full)
            self.right_selected.discard(full)
            self.refresh()
            self.say(f"Renommé → {new}")
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))
        return "break"

    def _clipboard_selection(self) -> List[Entry]:
        """Return the current pane selection for internal clipboard actions."""
        if self._typing():
            return []
        pane = RIGHT if self.active_pane == RIGHT else LEFT
        return self._selection_paths(pane)

    def cut_selected(self, event=None):
        sels = self._clipboard_selection()
        if not sels:
            if not self._typing():
                self.say("Couper - aucune sélection")
            return "break"
        self.clipboard_cut = [(full, is_dir) for (_, full, is_dir) in sels]
        self.clipboard_copy = None
        self.say(f"Couper: {len(sels)} élément(s). Allez au dossier cible puis collez.")
        return "break"

    def copy_selected(self, event=None):
        sels = self._clipboard_selection()
        if not sels:
            if not self._typing():
                self.say("Copier - aucune sélection")
            return "break"
        self.clipboard_copy = [(full, is_dir) for (_, full, is_dir) in sels]
        self.clipboard_cut = None
        self.say(f"Copier: {len(sels)} élément(s) prêt(s). Allez au dossier cible puis collez.")
        return "break"

    def paste_clipboard(self, event=None):
        if self._typing():
            return None
        mode = "cut" if self.clipboard_cut else "copy"
        clip = self.clipboard_cut or self.clipboard_copy
        if not clip:
            self.say("Presse-papiers vide.")
            return "break"
        done, failed, skipped = 0, 0, 0
        for src, is_dir in clip:
            base = os.path.basename(src.rstrip("\\/"))
            dest = os.path.join(self.cwd, base)
            if os.path.abspath(src) == os.path.abspath(dest):
                skipped += 1
                continue
            if os.path.exists(dest):
                skipped += 1
                continue
            # Éviter de coller un dossier dans lui-même.
            try:
                if is_dir and os.path.commonpath([os.path.abspath(src), os.path.abspath(self.cwd)]) == os.path.abspath(src):
                    skipped += 1
                    continue
            except Exception:
                pass
            try:
                if mode == "cut":
                    shutil.move(src, dest)
                elif is_dir:
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
                done += 1
            except Exception as e:
                failed += 1
                self.say(f"Coller échec {base}: {e}")
        if mode == "cut" and done > 0:
            self.clipboard_cut = None
        self.refresh()
        action = "déplacé(s)" if mode == "cut" else "copié(s)"
        self.say(f"Coller: {action} {done} | échec {failed} | ignoré(s) {skipped}")
        return "break"


def main() -> None:
    try:
        app = FileManagerApp()
        app.mainloop()
    except Exception:
        traceback.print_exc()
        try:
            messagebox.showerror(APP_NAME, traceback.format_exc())
        except Exception:
            pass


if __name__ == "__main__":
    main()
