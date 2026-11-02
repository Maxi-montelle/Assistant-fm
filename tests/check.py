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

# 2. Chances comparées au simulateur DoFocus (valeurs lues sur dofocus.fr, arrondies)
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
    assert max(abs(a - b) for a, b in zip(c, o)) <= 0.6, (st, rn, c, o)

# 3. Cas particuliers, valeurs données par le code du simulateur dofocus.fr
def case(name, exos, st, rn, level, o, changes=None):
    v2, mx2 = dict(v, **(changes or {})), dict(mx)
    v2.update(exos)
    for s in exos:
        mx2[s] = 0
    r = next(x for x in fm_core.runes(st) if x[0] == rn)
    c = fm_core.chances(v2, mx2, st, r, level, mn)[:3]
    assert max(abs(a - b) for a, b in zip(c, o)) <= 0.11, (name, c, o)

case("over", {}, "Dommages Critiques", "Do Cri", 200, (2.6, 42, 55.4), {"Dommages Critiques": 10})
case("exo PA = objet parfait", {"PA": 1}, "Vitalité", "Ra Vi", 200, (2, 46.3, 51.8))
case("1er % Do sorts", {}, "% Dommages aux sorts", "Do Per So", 200, (1.5, 17.5, 81))
case("2e % Do sorts", {"% Dommages aux sorts": 1}, "% Dommages aux sorts", "Do Per So", 200, (1, 0, 99))
case("exo PA", {}, "PA", "Ga Pa", 200, (1, 0, 99))
case("niveau < 170", {}, "Vitalité", "Ra Vi", 150, (25.7, 50, 24.3))
case("plafond de 101 de poids", {"Puissance": 50}, "% Dommages aux sorts", "Do Per So", 200, (0, 0, 0))

# 4. Les min / max voulus survivent à une lecture partielle (fenêtre cachée) et à un changement d'objet
S = fm_core.Session()
S.update(dict(v))
S.targets["Vitalité"] = (420, 450)
assert S.update({"Tacle": 9, "Retrait PM": 13}) is False and S.values == v, "lecture partielle prise pour un objet"
S.update({"Force": 50, "Agilité": 40, "Sagesse": 10})
assert S.targets.get("Vitalité") == (420, 450), "fourchettes effacées au changement d'objet"

# 5. Cases vides = max du jeu, sans jamais réécrire ce que le joueur a tapé
S.targets = {"Vitalité": (420, None), "Sagesse": (None, 38)}
S.maxes.update({"Vitalité": 450, "Sagesse": 40})
assert S.target("Vitalité") == (420, 450) and S.target("Sagesse") == (38, 38) and S.target("Force") == (S.maxes.get("Force", 0),) * 2
assert S.targets["Vitalité"] == (420, None)

print("Tous les tests passent.")
