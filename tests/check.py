"""Vérifications lancées par GitHub avant de publier une version.
python tests/check.py  -> s'arrête avec une erreur si la lecture ou les chances dérivent."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image  # noqa: E402

import fm_core  # noqa: E402
import fm_live  # noqa: E402

HERE = os.path.dirname(__file__)
err = fm_live.check_tesseract()
assert err is None, err

# 1. Lecture de la fenêtre de FM complète (tableau + historique)
img = Image.open(os.path.join(HERE, "fenetre.png")).convert("RGB")
cols = fm_live.find_columns(img)
assert cols, "colonnes Min / Modif. non trouvées"
table, hist = fm_live.split_capture(img, cols)
ranges, mins = {}, {}
text = fm_live.ocr(table)
vals = fm_core.parse_lines(text, ranges, mins)
expect = {"Vitalité": 394, "Intelligence": 96, "Sagesse": 25, "% Critique": 5, "Dommages Feu": 15,
          "% Résistance Terre": 5, "% Résistance Air": 6, "Tacle": 9, "Retrait PM": 13,
          "Dommages Critiques": 9, "Portée": -1}
assert vals == expect, f"stats lues : {vals}"
assert ranges["Vitalité"] == 450 and mins["Vitalité"] == 401, (ranges, mins)
assert fm_core.parse_reliquat(text) == 0.9
item, entries = fm_core.parse_history(fm_live.ocr(hist))
assert item == "HEAUME DE GUERRE", item
assert (-34, "Vitalité") in entries and len(entries) == 8, entries

# 2. Chances comparées au simulateur DoFocus (écart max 3 points)
L = {"Vitalité": (394, 401, 450), "Intelligence": (96, 81, 100), "Sagesse": (25, 31, 40), "% Critique": (5, 4, 5),
     "Portée": (-1, -1, -1), "Dommages Feu": (15, 11, 15), "% Résistance Terre": (5, 7, 10),
     "% Résistance Air": (6, 4, 7), "Tacle": (9, 11, 15), "Retrait PM": (13, 11, 15), "Dommages Critiques": (9, 7, 10)}
v = {k: x[0] for k, x in L.items()}
mn = {k: x[1] for k, x in L.items()}
mx = {k: x[2] for k, x in L.items()}
dofocus = [("Vitalité", "Vi", (2, 15, 83)), ("Vitalité", "Pa Vi", (2, 29, 69)), ("Vitalité", "Ra Vi", (23, 50, 27)),
           ("Intelligence", "Ine", (2, 15, 83)), ("Sagesse", "Sa", (2, 33, 65)), ("Sagesse", "Pa Sa", (43, 50, 6.8)),
           ("% Critique", "Cri", (2, 35, 63)), ("Portée", "Po", (2, 5, 93)), ("Dommages Feu", "Pa Do Feu", (2, 27, 71)),
           ("% Résistance Terre", "Ré Per Terre", (44, 50, 6.3)), ("% Résistance Air", "Ré Per Air", (23, 50, 27)),
           ("Tacle", "Tac", (44, 50, 5.9)), ("Retrait PM", "Ret Pme", (45, 50, 4.8)),
           ("Dommages Critiques", "Do Cri", (23, 50, 27)), ("Dommages Critiques", "Pa Do Cri", (2, 34, 64))]
for st, rn, o in dofocus:
    r = next(x for x in fm_core.runes(st) if x[0] == rn)
    c = fm_core.chances(v, mx, st, r, 200, mn)[:3]
    assert max(abs(a - b) for a, b in zip(c, o)) <= 3.1, (st, rn, c, o)

print("Tous les tests passent.")
