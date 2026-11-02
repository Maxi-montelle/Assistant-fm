"""Assistant FM Dofus 3, en temps réel.

Le programme REGARDE seulement une zone de ton écran (capture + lecture du texte).
Il ne lit ni la mémoire ni le réseau du jeu, ne modifie aucun fichier,
ne clique pas et n'appuie sur aucune touche à ta place.

Lancement :  python fm_live.py
Test sur une capture :  python fm_live.py --test capture.png
"""
import json
import os
import sys
import threading
import time

import mss
import pytesseract
from PIL import Image, ImageOps, ImageStat

import fm_core

from version import VERSION, CHANGELOG
import updater

# En version .exe : les fichiers fournis (Tesseract, langue) sont dans le dossier interne de l'exe,
# les réglages et les fichiers de debug à côté de l'exe.
FROZEN = getattr(sys, "frozen", False)
BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
INTERVAL = 0.7  # secondes entre deux lectures
MISS_LIMIT = 8  # lectures d'affilée sans une ligne avant de la considérer vraiment disparue
# stats proposees en over meme si l'objet ne les a pas
OVER_EXTRA = ["% Dommages aux sorts"]

# Chemin Windows par défaut de Tesseract
if os.name == "nt":
    for cand in (os.path.join(BUNDLE, "tesseract", "tesseract.exe"),
                 r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                 os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
                 os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe")):
        if os.path.exists(cand):
            pytesseract.pytesseract.tesseract_cmd = cand
            break
    try:  # captures nettes sur les écrans avec mise à l'échelle Windows
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


LANG = "fra"
# Fichier de langue française fourni avec le programme (dossier tessdata à côté de ce script)
LOCAL_TESSDATA = os.path.join(BUNDLE, "tessdata")
TESS_CONFIG = "--psm 6"
if os.path.exists(os.path.join(LOCAL_TESSDATA, "fra.traineddata")):
    # Variable d'environnement plutôt qu'une option : marche aussi avec des espaces dans le chemin (Windows)
    os.environ["TESSDATA_PREFIX"] = LOCAL_TESSDATA


def check_tesseract():
    """Renvoie None si tout va bien, sinon un message d'erreur clair."""
    global LANG
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return ("Tesseract introuvable. Installe-le depuis github.com/UB-Mannheim/tesseract/wiki "
                "(dossier par défaut), puis relance.")
    try:  # vrai test de lecture, avec le fichier de langue fourni
        pytesseract.image_to_string(Image.new("RGB", (60, 20), "white"), lang="fra", config=TESS_CONFIG)
        return None
    except Exception:
        pass
    LANG = "eng"
    return ("Langue française introuvable : vérifie que le dossier « tessdata » (avec fra.traineddata) "
            "est bien à côté de fm_live.py. Lecture en anglais en attendant (moins fiable).")


def prep(img):
    """Prépare l'image (texte clair sur fond sombre dans Dofus 3) pour la lecture."""
    g = ImageOps.grayscale(img)
    g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)
    if ImageStat.Stat(g).mean[0] < 128:  # fond sombre -> on inverse
        g = ImageOps.invert(g)
    return g.point(lambda p: 255 if p > 150 else 0)


def _cfg():
    return TESS_CONFIG if LANG == "fra" else "--psm 6"


def ocr(img):
    return pytesseract.image_to_string(prep(img), lang=LANG, config=_cfg())


def find_columns(img):
    """Repère dans la capture les en-têtes « Min » et « Modif. » du tableau de FM.
    Renvoie (x_debut_tableau, x_fin_tableau) en pixels de la capture, ou None."""
    d = pytesseract.image_to_data(prep(img), lang=LANG, config=_cfg(), output_type=pytesseract.Output.DICT)
    words = [(w.strip().lower().rstrip("."), d["left"][i] // 2, d["top"][i] // 2) for i, w in enumerate(d["text"])]
    mins = [(x, y) for w, x, y in words if w == "min"]
    if not mins:
        return None
    x_min, y_min = mins[0]
    modif = [x for w, x, y in words if w.startswith("modif") and abs(y - y_min) < 15 and x > x_min]
    return max(0, x_min - 18), (modif[0] - 6 if modif else img.width)


def split_capture(img, cols):
    """Coupe la capture en (tableau, historique) grâce aux colonnes repérées."""
    if not cols:
        return img, None
    left, right = cols
    table = img.crop((left, 0, max(left + 50, right), img.height))
    hist = img.crop((0, 0, left, img.height)) if left > 80 else None
    return table, hist


def test_mode(path):
    err = check_tesseract()
    if err:
        print("⚠", err)
    img = Image.open(path).convert("RGB")
    cols = find_columns(img)
    table, hist = split_capture(img, cols)
    print("Colonnes repérées :", cols)
    text = ocr(table)
    if hist is not None:
        it, ent = fm_core.parse_history(ocr(hist))
        print("Historique :", it, ent)
    ranges = {}
    print("----- Texte lu -----\n" + text)
    print("----- Stats reconnues -----")
    for s, v in fm_core.parse_lines(text, ranges).items():
        print(f"  {s:25} {v:>5}" + (f"   (max : {ranges[s]})" if s in ranges else "   (max non lu)"))
    print("Reliquat lu :", fm_core.parse_reliquat(text))


# ======================= Interface =======================
def run_app():
    import tkinter as tk
    from tkinter import ttk

    cfg = load_config()
    sess = fm_core.Session()
    sess.maxes.update(cfg.get("maxes", {}))
    sess.targets.update({k: tuple(v) for k, v in cfg.get("targets", {}).items()})
    max_fix = dict(cfg.get("max_fix", {}))  # max du jeu corrigés à la main (prioritaires sur la lecture)
    sess.maxes.update(max_fix)
    state = {"region": cfg.get("region"), "hist_region": cfg.get("hist_region"), "last_read": None,
             "stable": None, "running": True, "known": {}, "miss": {}, "hist": [], "item": None, "force": False}

    import tkinter.font as tkfont

    root = tk.Tk()
    root.title(f"Assistant FM v{VERSION}")
    root.attributes("-topmost", True)
    BG, BG2, FG, MUT, GOLD, OK, BLUE, RED = "#15110e", "#221b16", "#f3ebe0", "#b3a594", "#f0b54e", "#6cd08f", "#7ab8f0", "#f07a6a"
    root.configure(bg=BG)
    root.geometry(cfg.get("geometry", "420x660+40+40"))
    root.minsize(300, 160)

    zoom = cfg.get("zoom", 0)
    F = {k: tkfont.Font(family="Segoe UI", size=sz, weight=w) for k, (sz, w) in {
        "rune": (24, "bold"), "kick": (9, "bold"), "why": (11, "normal"), "puits": (16, "bold"),
        "txt": (10, "normal"), "bold": (10, "bold"), "small": (9, "normal"), "btn": (10, "bold")}.items()}
    BASE = {k: f.cget("size") for k, f in F.items()}

    def apply_zoom():
        for k, f in F.items():
            f.configure(size=max(7, BASE[k] + zoom))
        wrap = max(200, root.winfo_width() - 40) if root.winfo_width() > 50 else 380
        for l in (rune_lbl, why_lbl, status):
            l.config(wraplength=wrap)

    def btn(parent, text, cmd, **kw):
        return tk.Button(parent, text=text, command=cmd, font=F["btn"], bg="#3a2f24", fg=FG,
                         activebackground=GOLD, activeforeground="#1b1408", relief="flat", padx=8, pady=3, **kw)

    # ---- barre d'outils ----
    top = tk.Frame(root, bg=BG)
    top.pack(fill="x", padx=10, pady=(8, 4))
    btn(top, "📐 Zone", lambda: pick_region()).pack(side="left")
    btn(top, "📜 Histo", lambda: pick_region("hist_region")).pack(side="left", padx=(4, 0))
    btn(top, "🔍", lambda: state.update(debug=True)).pack(side="left", padx=(4, 0))
    goals = {"Mon jet": "jet", "Exo PA": "exo-PA", "Exo PM": "exo-PM", "Exo PO": "exo-Portée", "Over": "over"}
    cb = ttk.Combobox(top, values=list(goals), state="readonly", width=11, font=F["txt"])
    cb.set("Mon jet")
    cb.pack(side="left", padx=6)
    pause_btn = btn(top, "⏸", None, width=2)
    pause_btn.pack(side="right")
    compact_btn = btn(top, "▣", None, width=2)
    compact_btn.pack(side="right", padx=(0, 4))
    btn(top, "A+", lambda: set_zoom(1)).pack(side="right", padx=(0, 4))
    btn(top, "A−", lambda: set_zoom(-1)).pack(side="right", padx=(0, 2))

    over_fr = tk.Frame(root, bg=BG)
    over_stat = ttk.Combobox(over_fr, state="readonly", width=20, font=F["txt"])
    over_val = tk.Entry(over_fr, width=6, font=F["txt"])
    tk.Label(over_fr, text="Over sur", bg=BG, fg=FG, font=F["txt"]).pack(side="left")
    over_stat.pack(side="left", padx=4)
    tk.Label(over_fr, text="→ viser", bg=BG, fg=FG, font=F["txt"]).pack(side="left")
    over_val.pack(side="left", padx=4)

    # ---- carte de la rune (le plus visible) ----
    card = tk.Frame(root, bg=GOLD)
    card.pack(fill="x", padx=10, pady=(6, 4))
    kick = tk.Label(card, text="PASSE MAINTENANT", bg=GOLD, fg="#4a3410", font=F["kick"], anchor="w")
    kick.pack(fill="x", padx=12, pady=(8, 0))
    rune_lbl = tk.Label(card, text="", font=F["rune"], fg="#1b1408", bg=GOLD, wraplength=380, justify="left", anchor="w")
    rune_lbl.pack(fill="x", padx=12, pady=(0, 10))
    why_lbl = tk.Label(root, text="", fg=FG, bg=BG, font=F["why"], wraplength=380, justify="left", anchor="w")
    why_lbl.pack(fill="x", padx=12, pady=(2, 2))
    ch_fr = tk.Frame(root, bg=BG)
    ch_fr.pack(fill="x", padx=12, pady=(0, 4))
    ch_sc = tk.Label(ch_fr, text="", fg=OK, bg=BG, font=F["bold"])
    ch_sc.pack(side="left")
    ch_sn = tk.Label(ch_fr, text="", fg=BLUE, bg=BG, font=F["bold"])
    ch_sn.pack(side="left", padx=10)
    ch_ec = tk.Label(ch_fr, text="", fg=RED, bg=BG, font=F["bold"])
    ch_ec.pack(side="left")

    pf = tk.Frame(root, bg=BG)
    pf.pack(fill="x", padx=12, pady=(4, 2))
    puits_lbl = tk.Label(pf, text="Reliquat : 0", font=F["puits"], fg=BLUE, bg=BG)
    puits_lbl.pack(side="left")

    # ---- détails (masqués en mode compact) ----
    details = tk.Frame(root, bg=BG)
    details.pack(fill="both", expand=True)
    corr = tk.Frame(details, bg=BG)
    corr.pack(fill="x", padx=12)
    tk.Label(corr, text="Corriger le reliquat :", fg=MUT, bg=BG, font=F["small"]).pack(side="left")
    puits_e = tk.Entry(corr, width=6, font=F["small"])
    puits_e.pack(side="left", padx=4)
    lvl_e = tk.Entry(corr, width=4, font=F["small"])
    lvl_e.pack(side="right")
    lvl_e.insert(0, str(cfg.get("level", 200)))
    tk.Label(corr, text="Niveau objet :", fg=MUT, bg=BG, font=F["small"]).pack(side="right", padx=4)
    sess.level = int(cfg.get("level", 200))
    lines_fr = tk.Frame(details, bg=BG)
    lines_fr.pack(fill="x", padx=10, pady=(8, 0))
    tk.Label(details, text="Historique (jeu 🎮 + assistant)", fg=MUT, bg=BG, font=F["kick"], anchor="w").pack(fill="x", padx=12, pady=(8, 0))
    log_box = tk.Listbox(details, height=5, bg=BG2, fg=FG, borderwidth=0, highlightthickness=0, font=F["small"])
    log_box.pack(fill="both", expand=True, padx=10, pady=(2, 6))
    status = tk.Label(root, text="", fg=MUT, bg=BG, font=F["small"], wraplength=380, justify="left", anchor="w")
    status.pack(fill="x", padx=12, pady=(0, 8), side="bottom")

    state["compact"] = cfg.get("compact", False)

    def set_compact(v):
        state["compact"] = v
        if v:
            details.pack_forget()
        else:
            details.pack(fill="both", expand=True, before=status)
        compact_btn.config(text="▤" if v else "▣")
        persist()

    def set_zoom(d):
        nonlocal zoom
        zoom = max(-3, min(10, zoom + d))
        apply_zoom()
        persist()

    def persist():
        cfg["maxes"] = sess.maxes
        cfg["targets"] = {k: list(v) for k, v in sess.targets.items()}
        if state.get("item"):
            cfg.setdefault("targets_by_item", {})[fm_core.norm(state["item"])] = cfg["targets"]
        cfg["max_fix"] = max_fix
        cfg["region"] = state["region"]
        cfg["hist_region"] = state["hist_region"]
        cfg["geometry"] = root.geometry()
        cfg["zoom"] = zoom
        cfg["level"] = sess.level
        cfg["compact"] = state.get("compact", False)
        save_config(cfg)

    def set_target(stat, e_lo, e_hi):
        if not e_lo.get().strip() and not e_hi.get().strip():
            sess.targets.pop(stat, None)
            persist()
            refresh()
            return
        t_lo, t_hi = e_lo.get().strip(), e_hi.get().strip()
        try:
            lo = int(t_lo or t_hi)
            hi = int(t_hi or t_lo)
        except ValueError:
            return
        e_lo.dirty = e_hi.dirty = False
        hi = max(lo, hi)
        if sess.target(stat) != (lo, hi):
            m = sess.maxes.get(stat, 0)
            if (lo, hi) == (m, m):
                sess.targets.pop(stat, None)
            else:
                sess.targets[stat] = (lo, hi)
            persist()
            refresh()

    def set_game_max(stat, e):
        txt = e.get().strip()
        if not txt:
            max_fix.pop(stat, None)  # vide = on revient à la valeur lue à l'écran
        else:
            try:
                max_fix[stat] = int(txt)
            except ValueError:
                return
            sess.maxes[stat] = max_fix[stat]
        persist()
        refresh()

    def reset_targets():
        sess.targets.clear()
        persist()
        refresh()

    def flash(n=0):
        colors = ["#fff4d6", GOLD, "#fff4d6", GOLD]
        if n < len(colors):
            for w in (card, kick, rune_lbl):
                w.config(bg=colors[n])
            root.after(140, flash, n + 1)

    import queue
    ui_q = queue.Queue()

    def post(fn, *args):
        """Depuis un thread : demande à la fenêtre d'exécuter fn(*args) (Tkinter n'est pas thread-safe)."""
        ui_q.put((fn, args))

    def pump():
        try:
            while True:
                fn, args = ui_q.get_nowait()
                try:
                    fn(*args)
                except Exception as ex:
                    status.config(text=f"Erreur interne : {ex}", fg=RED)
        except queue.Empty:
            pass
        root.after(50, pump)

    rows = {}

    def set_entry(e, val):
        """Met à jour une case sans écraser ce que le joueur est en train de taper."""
        if getattr(e, "dirty", False) or root.focus_get() is e:
            return
        if e.get() != str(val):
            e.delete(0, "end")
            e.insert(0, str(val))

    def make_entry(on_commit):
        e = tk.Entry(lines_fr, width=5, font=F["txt"], bg=BG2, fg=FG, insertbackground=FG, relief="flat", justify="center")
        e.dirty = False

        def typed(ev):
            if ev.keysym in ("Return", "Tab", "KP_Enter"):
                return
            e.dirty = True
            # enregistré tout seul dès que tu arrêtes de taper (pas besoin d'Entrée)
            if getattr(e, "_job", None):
                root.after_cancel(e._job)
            e._job = root.after(700, commit)

        def commit(ev=None):
            if getattr(e, "_job", None):
                root.after_cancel(e._job)
                e._job = None
            if e.dirty:
                e.dirty = False
                on_commit()
        e.bind("<KeyRelease>", typed)
        e.bind("<Return>", commit)
        e.bind("<KP_Enter>", commit)
        e.bind("<FocusOut>", commit)
        return e

    def build_table(order):
        rows.clear()
        for w in lines_fr.winfo_children():
            w.destroy()
        for j, h in enumerate(("Stat", "Actuel", "Max jeu", "Min voulu", "Max voulu", "", "SC")):
            tk.Label(lines_fr, text=h, fg=MUT, bg=BG, font=F["small"], anchor="w").grid(row=0, column=j, sticky="w", padx=3)
        for i, s in enumerate(order, start=1):
            r = {}
            r["name"] = tk.Label(lines_fr, text=s, fg=FG, bg=BG, font=F["txt"], anchor="w")
            r["name"].grid(row=i, column=0, sticky="we")
            r["val"] = tk.Label(lines_fr, text="", bg=BG, font=F["bold"], width=5)
            r["val"].grid(row=i, column=1, sticky="we")
            r["max"] = make_entry(lambda s=s: set_game_max(s, rows[s]["max"]))
            r["max"].grid(row=i, column=2, padx=2, pady=1)
            r["lo"] = make_entry(lambda s=s: set_target(s, rows[s]["lo"], rows[s]["hi"]))
            r["lo"].grid(row=i, column=3, padx=2, pady=1)
            r["hi"] = make_entry(lambda s=s: set_target(s, rows[s]["lo"], rows[s]["hi"]))
            r["hi"].grid(row=i, column=4, padx=2, pady=1)
            r["etat"] = tk.Label(lines_fr, text="", bg=BG, font=F["bold"], width=9, anchor="w")
            r["etat"].grid(row=i, column=5, sticky="we")
            r["sc"] = tk.Label(lines_fr, text="", bg=BG, font=F["small"], width=5)
            r["sc"].grid(row=i, column=6, sticky="we")
            rows[s] = r
        if order:
            tk.Label(lines_fr, text="Tape tes valeurs : elles sont gardées toutes seules. Max jeu faux ? Corrige-le (vide = relu à l'écran).",
                     fg=MUT, bg=BG, font=F["small"], anchor="w", wraplength=300, justify="left").grid(
                row=len(order) + 1, column=0, columnspan=4, sticky="w", pady=(4, 0))
            btn(lines_fr, "↺ Max du jeu partout", reset_targets).grid(row=len(order) + 1, column=4, columnspan=3, sticky="e", pady=(4, 0))

    def refresh():
        rune, why = sess.advise()
        done = rune.startswith("✅")
        if rune != state.get("shown"):
            state["shown"] = rune
            flash()
        kick.config(text="TERMINÉ" if done else "PASSE MAINTENANT")
        rune_lbl.config(text=rune)
        why_lbl.config(text=why)
        c3 = sess.last_chances
        if c3 and not done:
            fmt = lambda x: f"{x:g}".replace(".", ",")
            ch_sc.config(text=f"SC {fmt(c3[0])} %")
            ch_sn.config(text=f"SN {fmt(c3[1])} %")
            ch_ec.config(text=f"EC {fmt(c3[2])} %")
        else:
            for l in (ch_sc, ch_sn, ch_ec):
                l.config(text="")
        puits_lbl.config(text=f"Reliquat : {sess.puits:g}".replace(".", ","))
        target = rune.split(" sur ")[-1] if " sur " in rune else None
        key = tuple(sess.values)
        if key != state.get("rows_key"):
            build_table(key)
            state["rows_key"] = key
        for i, (s, v) in enumerate(sess.values.items(), start=1):
            r = rows[s]
            m = sess.maxes.get(s, 0)
            lo, hi = sess.target(s)
            rbg = "#4a3818" if s == target else (BG2 if i % 2 else BG)
            if v < lo:
                etat, col = f"−{lo - v}", GOLD
            elif v > m:
                etat, col = f"✔ over +{v - m}", BLUE
            else:
                etat, col = "✔", OK
            r["name"].config(text=("▶ " if s == target else "") + s, bg=rbg, font=F["bold"] if s == target else F["txt"])
            r["val"].config(text=str(v), fg=col, bg=rbg)
            fixed = s in max_fix
            r["max"].config(font=F["bold"] if fixed else F["txt"], bg="#4a2e2e" if fixed else rbg, fg=FG if fixed else MUT)
            set_entry(r["max"], m)
            custom = s in sess.targets
            for e, val in ((r["lo"], lo), (r["hi"], hi)):
                e.config(font=F["bold"] if custom else F["txt"], bg="#2e3a4a" if custom else BG2)
                set_entry(e, val)
            r["etat"].config(text=etat, fg=col, bg=rbg)
            if s in fm_core.STATS:
                gap = max(1, hi - v) if v < hi else 1
                rr = fm_core.smart_rune(s, gap, sess.values, sess.maxes, sess.level, sess.mins)
                scl = fm_core.chances(sess.values, sess.maxes, s, rr, sess.level, sess.mins)[0]
                r["sc"].config(text=f"{scl:.0f}%", fg=OK if scl >= 30 else GOLD if scl >= 10 else RED, bg=rbg)
        lines_fr.grid_columnconfigure(0, weight=1)
        extra = [x for x in OVER_EXTRA if x not in sess.values]
        over_stat.config(values=extra + list(sess.values))
        log_box.delete(0, "end")
        for l in sess.log[:50]:
            log_box.insert("end", l)

    def on_goal(_=None):
        sess.goal = goals[cb.get()]
        if sess.goal == "over":
            over_fr.pack(after=top, fill="x", padx=10)
        else:
            over_fr.pack_forget()
        refresh()

    def on_over_stat(_=None):
        # nouvelle stat choisie : on propose tout de suite une valeur visée cohérente
        st = over_stat.get()
        if st and st != sess.over_stat:
            m = sess.maxes.get(st, 0)
            over_val.delete(0, "end")
            over_val.insert(0, str(m + 1))
        on_over()

    def on_over(_=None):
        sess.over_stat = over_stat.get()
        try:
            sess.over_target = int(over_val.get())
        except ValueError:
            sess.over_target = 0
        refresh()

    def on_puits(_=None):
        try:
            sess.puits = max(0.0, float(puits_e.get().replace(",", ".")))
        except ValueError:
            return
        puits_e.delete(0, "end")
        refresh()

    def toggle_pause():
        state["running"] = not state["running"]
        pause_btn.config(text="⏸" if state["running"] else "▶")

    cb.bind("<<ComboboxSelected>>", on_goal)
    over_stat.bind("<<ComboboxSelected>>", on_over_stat)
    over_val.bind("<Return>", on_over)
    over_val.bind("<KeyRelease>", on_over)  # pas besoin d'appuyer sur Entrée
    puits_e.bind("<Return>", on_puits)

    def on_level(_=None):
        try:
            sess.level = int(lvl_e.get())
        except ValueError:
            return
        persist()
        refresh()
    lvl_e.bind("<Return>", on_level)
    lvl_e.bind("<KeyRelease>", on_level)
    pause_btn.config(command=toggle_pause)
    compact_btn.config(command=lambda: set_compact(not state["compact"]))
    root.bind("<Configure>", lambda e: apply_zoom() if e.widget is root else None)
    apply_zoom()
    if state["compact"]:
        set_compact(True)

    def pick_region(key="region"):
        """Plein écran semi-transparent : glisse la souris sur la zone à lire."""
        with mss.mss() as sct:
            mon = sct.monitors[0]
        sel = tk.Toplevel(root)
        sel.overrideredirect(True)
        sel.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
        sel.attributes("-topmost", True)
        sel.attributes("-alpha", 0.3)
        c = tk.Canvas(sel, bg="black", cursor="cross", highlightthickness=0)
        c.pack(fill="both", expand=True)
        c.create_text(mon["width"] // 2, 40, text=("Encadre TOUTE la fenêtre de forgemagie (historique + tableau). Échap pour annuler"
                                 if key == "region" else "Encadre le panneau HISTORIQUE à gauche de la fenêtre de FM (Échap pour annuler)"), fill="white", font=("Segoe UI", 18, "bold"))
        pts = {}

        def down(e):
            pts["x"], pts["y"] = e.x_root, e.y_root
            pts["r"] = c.create_rectangle(e.x, e.y, e.x, e.y, outline=GOLD, width=3)

        def drag(e):
            c.coords(pts["r"], pts["x"] - mon["left"], pts["y"] - mon["top"], e.x, e.y)

        def up(e):
            x1, y1 = min(pts["x"], e.x_root), min(pts["y"], e.y_root)
            x2, y2 = max(pts["x"], e.x_root), max(pts["y"], e.y_root)
            sel.destroy()
            if x2 - x1 > 20 and y2 - y1 > 20:
                state[key] = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
                state["cols"] = None
                persist()

        c.bind("<ButtonPress-1>", down)
        c.bind("<B1-Motion>", drag)
        c.bind("<ButtonRelease-1>", up)
        sel.bind("<Escape>", lambda e: sel.destroy())
        sel.focus_force()

    def worker():
        with mss.mss() as sct:
            while True:
                time.sleep(INTERVAL)
                if not state["running"] or not state["region"]:
                    continue
                try:
                    shot = sct.grab(state["region"])
                    full = Image.frombytes("RGB", shot.size, shot.rgb)
                    state["n"] = state.get("n", 0) + 1
                    if state.get("cols") is None or state["n"] % 15 == 0:
                        state["cols"] = find_columns(full) or False
                    img, auto_hist = split_capture(full, state["cols"])
                    ranges, mins = {}, {}
                    text = ocr(img)
                    vals = fm_core.parse_lines(text, ranges, mins)
                    state["mins_read"] = mins
                    rel = fm_core.parse_reliquat(text)
                    hist_text, himg = "", None
                    if auto_hist is not None and not state.get("hist_region"):
                        himg = auto_hist
                        hist_text = ocr(himg)
                    elif state.get("hist_region"):
                        hs = sct.grab(state["hist_region"])
                        himg = Image.frombytes("RGB", hs.size, hs.rgb)
                        hist_text = ocr(himg)
                    if state.get("debug"):
                        if himg is not None:
                            himg.save(os.path.join(HERE, "debug_historique.png"))
                        state["debug"] = False
                        full.save(os.path.join(HERE, "debug_capture.png"))
                        with open(os.path.join(HERE, "debug_texte.txt"), "w", encoding="utf-8") as f:
                            f.write(f"Zone : {state['region']}\n\n{text}\n\nStats : {vals}\nMax : {ranges}\nReliquat : {rel}\n"
                                    f"\n--- Historique ({state.get('hist_region')}) ---\n{hist_text}\n")
                        post(lambda kw: status.config(**kw), {"text": "🔍 debug_capture.png et debug_texte.txt enregistrés dans le dossier du programme.", "fg": "#6aa8e0"})
                        continue
                except Exception as ex:
                    post(lambda kw: status.config(**kw), {"text": f"Erreur de lecture : {ex}"})
                    continue
                post(handle_hist, hist_text)
                post(handle, vals, ranges, rel)

    def handle_hist(text):
        """Lit le panneau Historique : nom de l'objet + une ligne par effet de rune."""
        if not text:
            return
        item, entries = fm_core.parse_history(text)
        # Un AUTRE nom d'objet doit être lu 3 fois d'affilée avant d'y croire :
        # une seule capture mal lue ne doit pas tout remettre à zéro (fourchettes comprises).
        if item and state["item"] and not fm_core.same_item(item, state["item"]):
            cand = state.get("item_cand")
            if cand and fm_core.same_item(item, cand[0]):
                state["item_cand"] = (cand[0], cand[1] + 1)
            else:
                state["item_cand"] = (item, 1)
            if state["item_cand"][1] < 3:
                item = None  # on ignore ce nom pour l'instant
        else:
            state["item_cand"] = None
        if item and state["item"] and not fm_core.same_item(item, state["item"]):
            state["item_cand"] = None
            persist()  # garde les fourchettes de l'ancien objet
            goal, ost, otg, lvl = sess.goal, sess.over_stat, sess.over_target, sess.level
            sess.__init__()
            sess.goal, sess.over_stat, sess.over_target, sess.level = goal, ost, otg, lvl
            saved = cfg.get("targets_by_item", {}).get(fm_core.norm(item))
            if saved:
                sess.targets.update({k: tuple(v) for k, v in saved.items()})
            state["known"].clear(); state["miss"].clear(); state["stable"] = None; state["order"] = []
            state["hist"] = []
            sess.log.insert(0, f"🎮 Nouvel objet : {item}")
        if item and (not state["item"] or not fm_core.same_item(item, state["item"])):
            state["item"] = item
            root.title(f"Assistant FM v{VERSION} – {item.title()}")
        # 2 lectures identiques d'affilée avant d'y croire (une ligne mal lue ne crée pas de faux résultat)
        if entries != state.get("hist_last"):
            state["hist_last"] = entries
            return
        old = state["hist"]
        if entries == old:
            return
        added = fm_core.history_added(old, entries)
        if added:
            kind, det = fm_core.describe_result(added)
            sess.log.insert(0, f"🎮 {kind} : {det}")
            state["force"] = True        # accepter la prochaine lecture des stats sans attendre
            state["hist_logged"] = True  # le résultat vient du jeu : pas de doublon calculé
        elif added is None and not entries:
            sess.log.insert(0, "🎮 Historique vidé")
        state["hist"] = entries
        refresh()

    def stabilize(vals):
        """Une ligne qui manque sur UNE lecture (erreur d'OCR) est gardée avec sa dernière valeur.
        Elle n'est retirée que si elle manque MISS_LIMIT lectures d'affilée."""
        known, miss = state["known"], state["miss"]
        if known and len(set(vals) & set(known)) < max(1, len(known) // 2):
            known.clear()  # nouvel objet
            miss.clear()
            state["order"] = []
        for k, v in vals.items():
            known[k] = v
            miss[k] = 0
        for k in list(known):
            if k not in vals:
                miss[k] = miss.get(k, 0) + 1
                if miss[k] >= MISS_LIMIT:
                    del known[k]
                    miss.pop(k, None)
        # ordre des lignes = ordre du jeu (de haut en bas)
        order = state.setdefault("order", [])
        order[:] = [k for k in order if k in known]
        seq = list(vals)  # ordre de lecture à l'écran
        if set(seq) == set(known):
            order[:] = seq  # lecture complète : c'est la référence
        else:
            for i, k in enumerate(seq):
                if k in order:
                    continue
                prev = next((p for p in reversed(seq[:i]) if p in order), None)
                order.insert(order.index(prev) + 1 if prev else 0, k)
        return {k: known[k] for k in order}

    def handle(vals, ranges, rel):
        if vals:
            nread = len(vals)
            vals = stabilize(vals)
        if not vals:
            status.config(text="⚠ Aucune stat lue : vérifie la zone (📐) et que la fenêtre de FM est ouverte.", fg=RED)
            return
        rtxt = "lu" if rel is not None else "NON lu (inclus-le dans la zone)"
        htxt = f" · historique : {len(state['hist'])} ligne(s)" if (state["hist_region"] or state.get("cols")) else ""
        status.config(text=f"● {nread}/{len(vals)} lignes lues · reliquat {rtxt}{htxt} · {time.strftime('%H:%M:%S')}", fg=OK if rel is not None else GOLD)
        # On attend 2 lectures identiques d'affilée pour ignorer les animations et les erreurs de lecture
        # 1re lecture : conseil tout de suite. Ensuite, 2 lectures identiques d'affilée
        # avant de compter une rune (ignore les animations et les erreurs de lecture).
        first = not sess.values or state["force"]
        state["force"] = False
        if not first and vals != state["last_read"]:
            state["last_read"] = vals
            return
        state["last_read"] = vals
        if vals == state["stable"]:
            if rel is not None and rel != sess.puits:
                sess.puits = rel
                refresh()
            return
        state["stable"] = vals
        for s, m in ranges.items():
            if s not in max_fix:
                sess.maxes[s] = m
        sess.mins.update(state.get("mins_read") or {})
        sess.quiet = state.pop("hist_logged", False)
        if not sess.update(vals, rel) and rel is not None:
            sess.puits = rel  # reliquat affiche par le jeu = puits exact
        for s, v in vals.items():  # premières lectures : max inconnu -> valeur actuelle, à corriger
            sess.maxes.setdefault(s, v)
        persist()
        refresh()

    pump()
    upd_bar = tk.Frame(root, bg="#2e3a4a")
    upd_lbl = tk.Label(upd_bar, text="", bg="#2e3a4a", fg=FG, font=F["bold"], anchor="w", justify="left")
    upd_lbl.pack(side="left", padx=8, pady=4, fill="x", expand=True)
    upd_btn = btn(upd_bar, "Mettre à jour", None)
    upd_btn.pack(side="right", padx=6, pady=4)

    def show_update(info):
        ver, url, notes = info
        notes = "\n".join(l.strip() for l in notes.replace("**", "").replace("\r", "").splitlines() if l.strip())
        upd_lbl.config(text=f"⬇ Version {ver} disponible" + (f"\n{notes[:200]}" if notes else ""))
        upd_btn.config(command=lambda: do_update(url))
        upd_bar.pack(fill="x", padx=10, pady=(0, 4), after=top)

    def do_update(url):
        upd_btn.config(state="disabled")
        upd_lbl.config(text="Téléchargement de la mise à jour…")

        def run():
            try:
                updater.install(url, progress=lambda x: post(lambda kw: upd_lbl.config(**kw), {"text": f"Téléchargement… {x:.0%}"}))
                post(lambda: (persist(), root.destroy()))
            except Exception as ex:
                post(lambda kw: upd_lbl.config(**kw), {"text": f"Échec de la mise à jour : {ex}"})
                post(lambda kw: upd_btn.config(**kw), {"state": "normal"})
        threading.Thread(target=run, daemon=True).start()

    def check_update():
        try:
            info = updater.check_latest()
        except Exception as ex:
            post(lambda: (sess.log.insert(0, f"Mise à jour : vérification impossible ({ex})"), refresh()))
            return
        if info:
            post(show_update, info)
        else:
            post(lambda: (sess.log.insert(0, f"Assistant FM v{VERSION} : à jour"), refresh()))
    threading.Thread(target=check_update, daemon=True).start()

    # nouveautés affichées une fois après une mise à jour
    if cfg.get("seen_version") != VERSION:
        cfg["seen_version"] = VERSION
        sess.log.insert(0, f"Nouveautés : {CHANGELOG.splitlines()[0]}")
        save_config(cfg)

    root.protocol("WM_DELETE_WINDOW", lambda: (persist(), root.destroy()))
    threading.Thread(target=worker, daemon=True).start()
    err = check_tesseract()
    if err:
        status.config(text="⚠ " + err, fg="#e06a5a")
    if not state["region"]:
        rune_lbl.config(text="Clique sur 📐 Zone")
        why_lbl.config(text="Puis encadre la liste des stats de ton objet dans la fenêtre de forgemagie.")
    else:
        refresh()
    root.mainloop()


def selftest(path):
    """Utilisé par GitHub pour vérifier l'exe : code de sortie 0 si la capture est bien lue."""
    try:
        if check_tesseract():
            sys.exit(2)
        img = Image.open(path).convert("RGB")
        table, _ = split_capture(img, find_columns(img))
        vals = fm_core.parse_lines(ocr(table))
        sys.exit(0 if len(vals) >= 10 else 1)
    except SystemExit:
        raise
    except Exception:
        sys.exit(3)


def checkupdate_test():
    """Utilisé par GitHub : se fait passer pour une très vieille version et vérifie
    que l'exe voit bien la dernière version publiée (réseau + certificats OK)."""
    updater.VERSION = "0.0.1"
    try:
        info = updater.check_latest(timeout=20)
    except Exception:
        sys.exit(4)
    sys.exit(0 if info else 5)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--checkupdate":
        checkupdate_test()
    elif len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "--test":
        test_mode(sys.argv[2])
    else:
        run_app()
