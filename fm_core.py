"""Logique de l'assistant FM : lecture du texte, suivi du puits, conseils.
Aucun lien avec le jeu : ce module ne travaille que sur du texte et des nombres."""
import re
import unicodedata
import difflib

# nom canonique : (poids par point, [(rune, gain), ...], [alias lus a l'ecran])
STATS = {
    "Vitalité": (0.2, [("Vi", 5), ("Pa Vi", 15), ("Ra Vi", 50)], []),
    "Force": (1, [("Fo", 1), ("Pa Fo", 3), ("Ra Fo", 10)], []),
    "Intelligence": (1, [("Ine", 1), ("Pa Ine", 3), ("Ra Ine", 10)], []),
    "Chance": (1, [("Cha", 1), ("Pa Cha", 3), ("Ra Cha", 10)], []),
    "Agilité": (1, [("Age", 1), ("Pa Age", 3), ("Ra Age", 10)], []),
    "Sagesse": (3, [("Sa", 1), ("Pa Sa", 3), ("Ra Sa", 10)], []),
    "Puissance": (2, [("Pui", 1), ("Pa Pui", 3), ("Ra Pui", 10)], []),
    "Prospection": (3, [("Prospe", 1), ("Pa Prospe", 3)], []),
    "Initiative": (0.1, [("Ini", 10), ("Pa Ini", 30), ("Ra Ini", 100)], []),
    "Pods": (0.25, [("Pod", 10), ("Pa Pod", 30), ("Ra Pod", 100)], []),
    "PA": (100, [("Ga Pa", 1)], ["Point d'Action", "Points d'Action"]),
    "PM": (90, [("Ga Pme", 1)], ["Point de Mouvement", "Points de Mouvement"]),
    "Portée": (51, [("Po", 1)], ["PO"]),
    "Invocations": (30, [("Invo", 1)], ["Invocation", "Invocations"]),
    "Dommages": (20, [("Do", 1)], []),
    "Soins": (10, [("So", 1)], []),
    "% Critique": (10, [("Cri", 1)], ["Critique", "Coups Critiques"]),
    "Dommages Critiques": (5, [("Do Cri", 1), ("Pa Do Cri", 3)], []),
    "Résistance Critiques": (2, [("Ré Cri", 1), ("Pa Ré Cri", 3)], ["Résistances Critiques"]),
    "Dommages Poussée": (5, [("Do Pou", 1), ("Pa Do Pou", 3)], []),
    "Résistance Poussée": (2, [("Ré Pou", 1), ("Pa Ré Pou", 3)], ["Résistances Poussée"]),
    "Tacle": (4, [("Tac", 1), ("Pa Tac", 3)], []),
    "Fuite": (4, [("Fui", 1), ("Pa Fui", 3)], []),
    "Retrait PA": (7, [("Ret Pa", 1), ("Pa Ret Pa", 3)], []),
    "Retrait PM": (7, [("Ret Pme", 1), ("Pa Ret Pme", 3)], []),
    "Esquive PA": (7, [("Ré Pa", 1), ("Pa Ré Pa", 3)], []),
    "Esquive PM": (7, [("Ré Pme", 1), ("Pa Ré Pme", 3)], []),
    "% Dommages mêlée": (15, [("Do Per Mé", 1)], []),
    "% Dommages distance": (15, [("Do Per Di", 1)], []),
    "% Dommages d'armes": (15, [("Do Per Ar", 1)], []),
    "% Dommages aux sorts": (15, [("Do Per So", 1)], ["% Do sorts", "% Dommages sorts", "% Dommages de sorts", "Dommages aux sorts"]),
    "% Résistance mêlée": (15, [("Ré Per Mé", 1)], []),
    "% Résistance distance": (15, [("Ré Per Di", 1)], []),
}
for el, r in [("Terre", "Terre"), ("Feu", "Feu"), ("Eau", "Eau"), ("Air", "Air"), ("Neutre", "Neutre")]:
    STATS[f"Dommages {el}"] = (5, [(f"Do {r}", 1), (f"Pa Do {r}", 3)], [])
    STATS[f"Résistance {el}"] = (2, [(f"Ré {r}", 1), (f"Pa Ré {r}", 3)], [f"Résistances {el}"])
    STATS[f"% Résistance {el}"] = (6, [(f"Ré Per {r}", 1)], [])

EXO_STATS = ("PA", "PM", "Portée")


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("’", "'")
    words = re.sub(r"[^a-z0-9%' ]+", " ", s).split()
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words)


_ALIASES = {}
for name, (_, _, al) in STATS.items():
    for a in [name] + al:
        _ALIASES[norm(a)] = name
        if name.startswith("% "):
            _ALIASES[norm(a.replace("% ", ""))] = _ALIASES.get(norm(a.replace("% ", "")), name)

# "valeur [%] Nom de la stat" ; le signe moins doit etre colle au nombre (sinon c'est une icone)
STAT_RE = re.compile(r"(?:(-)|(?<![\w-]))(\d{1,4})\s*(%?)\s*([A-Za-zÀ-ÿ'’][A-Za-zÀ-ÿ'’ .]+)")
NUM_TOKEN = re.compile(r"-?[0-9ilIoOS|]{1,4}")
RELIQUAT_RE = re.compile(r"reliquat\s*[:;]?\s*(\d+(?:[.,]\d+)?)", re.I)
_FIX = str.maketrans({"i": "1", "l": "1", "I": "1", "|": "1", "o": "0", "O": "0", "S": "5"})


def match_stat(text, percent):
    key = norm(("% " if percent else "") + text)
    if key in _ALIASES:
        return _ALIASES[key]
    best = difflib.get_close_matches(key, _ALIASES.keys(), n=1, cutoff=0.78)
    return _ALIASES[best[0]] if best else None


def _to_int(tok):
    t = tok.translate(_FIX)
    return int(t) if re.fullmatch(r"-?\d+", t) and any(c.isdigit() for c in tok) else None


def parse_lines(ocr_text, ranges=None, mins=None):
    """Transforme le texte lu a l'ecran en {stat: valeur}.
    Lignes de la fenetre FM de Dofus 3 : "Min Max [icone] Valeur Stat".
    Si `ranges` est un dict, il recoit {stat: max} lu dans la colonne Max."""
    found = {}
    for raw in ocr_text.splitlines():
        hit = None
        for m in STAT_RE.finditer(raw):
            stat = match_stat(m.group(4).strip(" ."), bool(m.group(3)))
            if stat:
                hit = (m, stat)
                break
        if not hit:
            continue
        m, stat = hit
        if stat in found:
            continue
        found[stat] = int(m.group(2)) * (-1 if m.group(1) else 1)
        if ranges is not None:
            nums = [n for n in (_to_int(t) for t in NUM_TOKEN.findall(raw[:m.start()])) if n is not None]
            # colonnes Min et Max : parmi les paires de nombres voisins avec min <= max,
            # on garde celle au max le plus haut (ignore un bord ou une icône lus comme un chiffre)
            pairs = [(a, b) for a, b in zip(nums, nums[1:]) if a <= b]
            if pairs:
                lo_, hi_ = max(pairs, key=lambda p: p[1])
                ranges[stat] = hi_
                if mins is not None:
                    mins[stat] = lo_
    return found


def same_item(a, b):
    """Même objet malgré une erreur de lecture (« HEAUME DE GUERRE » / « HEAUME DE GUERRF »)."""
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() >= 0.8


def parse_reliquat(ocr_text):
    m = RELIQUAT_RE.search(ocr_text)
    return float(m.group(1).replace(",", ".")) if m else None


HIST_SKIP = ("vider", "historique", "pas d'historique", "actuellement", "costumage", "niv")


def parse_history(ocr_text):
    """Panneau Historique de la FM (Dofus 3).
    Renvoie (nom de l'objet ou None, [(valeur, stat), ...] dans l'ordre affiché)."""
    item, entries = None, []
    for raw in ocr_text.splitlines():
        line = " ".join(raw.split())
        if not line or any(k in line.lower() for k in HIST_SKIP):
            continue
        hit = None
        for m in STAT_RE.finditer(line):
            st = match_stat(m.group(4).strip(" ."), bool(m.group(3)))
            if st:
                hit = (int(m.group(2)) * (-1 if m.group(1) else 1), st)
                break
        if hit:
            entries.append(hit)
        elif not entries:
            caps = re.findall(r"[A-ZÀ-Ý][A-ZÀ-Ý'’\- ]{3,}", line)
            if caps:
                item = " ".join(w for w in max(caps, key=len).split() if len(w) > 1)
    return item, entries


def history_added(old, new):
    """Lignes ajoutées entre deux lectures de l'historique.
    Gère le défilement : quand le panneau est plein, les plus anciennes sortent par le haut.
    On cherche le plus grand recouvrement entre la fin de l'ancien et le début du nouveau.
    Renvoie [] si rien de neuf, None si on ne peut pas raccorder (historique vidé, etc.)."""
    if new == old:
        return []
    if not old:
        return list(new)
    for k in range(min(len(old), len(new)), 0, -1):
        if old[-k:] == new[:k]:
            return list(new[k:])
    return None


def describe_result(new_entries):
    """Résume les nouvelles lignes de l'historique : type de résultat + détail."""
    gains = [(v, s) for v, s in new_entries if v > 0]
    losses = [(v, s) for v, s in new_entries if v < 0]
    kind = "Succès critique" if gains and not losses else "Succès neutre" if gains else "Échec"
    det = ", ".join(f"{v:+d} {s}" for v, s in new_entries)
    return kind, det


def weight(stat):
    return STATS[stat][0]


def runes(stat):
    return STATS[stat][1]


def best_rune(stat, gap):
    pick = runes(stat)[0]
    for r in runes(stat):
        if r[1] <= gap:
            pick = r
    return pick


def smart_rune(stat, gap, values, maxes, level, mins=None):
    """Parmi les runes qui ne dépassent pas l'écart, la meilleure : plus de succès critique,
    puis moins d'échec critique, puis la plus grosse (moins de clics)."""
    ok = [r for r in runes(stat) if r[1] <= gap] or [runes(stat)[0]]
    def key(r):
        sc, sn, ec, _ = chances(values, maxes, stat, r, level, mins)
        return (sc, -ec, r[1])
    return max(ok, key=key)


# ===================== Formule de chances =====================
# Base : vidéo « J'ai CRACKÉ le secret de la forgemagie DOFUS » (DoFocus, ~225 000 clics analysés),
# puis calée sur les pourcentages affichés par le simulateur dofocus.fr (Heaume de Guerre niv. 200).
# Ce n'est PAS la formule officielle d'Ankama : c'est une estimation.
#
#   difficulté D = 5
#     + 45   si, APRÈS la rune, la ligne est à 80 % ou plus de son jet (entre min et max)
#     + 30 + 4 × poids au-dessus du max                     (over ; poids divisé par 2 sur une ligne négative)
#     + 10,5 × (valeur de la ligne / valeur de la rune − 14)  si ce rapport dépasse 14 (règle du ×14)
#     + 60 × (qualité des AUTRES lignes)^12                 (qualité = Σ poids actuels / Σ poids max)
#     − 20   si l'objet est sous le niveau 170
#   hors over, D est plafonnée à 166.
#   succès critique = (100 − D) / 2, jamais sous 2 % (sauf objet exo PA/PM/PO)
#   échec critique  = D / 2
#   succès neutre   = le reste (50 % tant que D ≤ 96)

def item_quality(values, maxes, exclude=None):
    """0 = objet vide, 1 = toutes les autres lignes au max (pondéré par le poids)."""
    num = den = 0.0
    for s, v in values.items():
        m = maxes.get(s, 0)
        if s == exclude or m <= 0 or s not in STATS:
            continue
        num += weight(s) * max(0, min(v, m))
        den += weight(s) * m
    return num / den if den else 0.0


def has_exo(values, maxes):
    return any(values.get(s, 0) > 0 and maxes.get(s, 0) <= 0 for s in EXO_STATS)


def difficulty(values, maxes, stat, rune, level=200, mins=None):
    gain = rune[1]
    w = weight(stat)
    v = values.get(stat, 0)
    m = maxes.get(stat, 0)
    mn = (mins or {}).get(stat)
    new = v + gain
    d = 5.0
    # palier des 80 % du jet, mesuré après la rune
    if mn is not None and m > mn:
        jet = (new - mn) / (m - mn)
    elif m > 0:
        jet = new / m
    else:
        jet = 9.0
    if jet >= 0.8:
        d += 45
    # over
    over = 0.0
    if new > m:
        over = (new - max(m, v)) * w * (0.5 if v < 0 else 1)
        d += 30 + 4 * over
    # règle du ×14
    if v > 0 and v / gain > 14:
        d += 10.5 * (v / gain - 14)
    # qualité des autres lignes (objet exo PA/PM/PO = parfait)
    exo = has_exo(values, maxes) and stat not in EXO_STATS
    q = 1.0 if exo else item_quality(values, maxes, exclude=stat)
    d += 60 * q ** 12
    if level < 170:
        d -= 20
    if not over:
        d = min(d, 166.0)
    return d, exo


def chances(values, maxes, stat, rune, level=200, mins=None):
    """Renvoie (succès critique %, succès neutre %, échec critique %, difficulté)."""
    d, exo = difficulty(values, maxes, stat, rune, level, mins)
    sc = (100 - d) / 2
    sc = max(0.0, sc) if exo else max(2.0, sc)
    sc = min(sc, 50.0)
    ec = min(max(0.0, d / 2), 100 - sc)
    sn = max(0.0, 100 - sc - ec)
    return round(sc, 1), round(sn, 1), round(ec, 1), round(d)


class Session:
    """Garde les valeurs, les max, le puits et l'historique."""

    def __init__(self):
        self.values = {}   # stat -> valeur actuelle
        self.maxes = {}    # stat -> max du jet (0 = stat exo, absente de base)
        self.puits = 0.0
        self.goal = "jet"  # jet | exo-PA | exo-PM | exo-Portée | over
        self.over_stat = None
        self.over_target = 0
        self.targets = {}  # stat -> (min voulu, max voulu) choisis par le joueur
        self.log = []
        self.last_advice = ""
        self.quiet = False  # True quand l'historique du jeu sert de journal
        self.level = 200     # niveau de l'objet (formule de chances)
        self.mins = {}       # colonne Min du jeu
        self.last_chances = None

    def update(self, new_values, reliquat=None):
        """Appelee quand une nouvelle lecture STABLE differe de la precedente.
        Renvoie True si le changement a ete compte comme une rune passee."""
        if not self.values:
            self.values = dict(new_values)
            for s, v in new_values.items():
                self.maxes.setdefault(s, v)
            return False
        stats = set(self.values) | set(new_values)
        # objet different (moins de la moitie des lignes en commun) -> on repart a zero
        common = set(self.values) & set(new_values)
        if len(common) < max(1, len(self.values) // 2):
            goal, os_, ot, lvl, tg = self.goal, self.over_stat, self.over_target, self.level, self.targets
            self.__init__()
            self.goal, self.over_stat, self.over_target, self.level = goal, os_, ot, lvl
            self.targets = {k: v for k, v in tg.items() if k in new_values}
            self.update(new_values)
            self.log.insert(0, "Nouvel objet détecté, puits remis à 0")
            return False
        lost = gained = 0.0
        changes = []
        for s in stats:
            d = new_values.get(s, 0) - self.values.get(s, 0)
            if d < 0:
                lost += -d * weight(s)
                changes.append(f"{s} {d}")
            elif d > 0:
                gained += d * weight(s)
                changes.append(f"{s} +{d}")
            self.maxes.setdefault(s, 0)
        if not changes:
            return False
        old = self.puits
        self.puits = reliquat if reliquat is not None else max(0.0, self.puits + lost - gained)
        res = "Succès critique" if gained and not lost else "Succès neutre" if gained else "Échec"
        if not self.quiet:
            self.log.insert(0, f"{self.last_advice} → {res} ({', '.join(changes)}) puits {old:g}→{self.puits:g}")
        self.values = {s: v for s, v in new_values.items()}
        return True

    # ---------- conseils ----------
    def target(self, s):
        """Fourchette voulue (min, max) : celle du joueur, sinon le max du jeu."""
        m = self.maxes.get(s, 0)
        lo, hi = self.targets.get(s, (m, m))
        return lo, max(lo, hi)

    def _lines(self):
        return [(s, self.values.get(s, 0), self.target(s)[1]) for s in self.values]

    def _advise_jet(self, exclude=None):
        todo = []
        for s, c in self.values.items():
            lo, hi = self.target(s)
            if c < lo and s != exclude:
                todo.append((s, c, lo, hi))
        if not todo:
            return None
        # D'après la formule : sous 80 % du max, une rune passe ~47 % du temps -> on monte
        # d'abord toutes les lignes ensemble jusqu'à 80 %, puis on finit par les plus faciles.
        def score(x):
            st, cur, lo_, hi_ = x
            r_ = smart_rune(st, hi_ - cur, self.values, self.maxes, self.level, self.mins)
            sc_ = chances(self.values, self.maxes, st, r_, self.level, self.mins)[0]
            m_ = self.maxes.get(st, 0)
            under80 = m_ > 0 and cur < 0.8 * m_
            return (0 if under80 else 1, -sc_, -weight(st))
        todo.sort(key=score)
        s, c, lo, hi = todo[0]
        r = smart_rune(s, hi - c, self.values, self.maxes, self.level, self.mins)
        m80 = self.maxes.get(s, 0)
        if m80 > 0 and c < 0.8 * m80:  # ne pas franchir 80 % avec une grosse rune si une plus petite y arrive pile
            gap80 = int(0.8 * m80) - c
            if gap80 > 0 and r[1] > gap80:
                r2 = smart_rune(s, gap80, self.values, self.maxes, self.level, self.mins)
                if r2[1] <= gap80 and chances(self.values, self.maxes, s, r2, self.level, self.mins)[0] >= \
                        chances(self.values, self.maxes, s, r, self.level, self.mins)[0]:
                    r = r2
        rng = f"{lo}" if lo == hi else f"{lo}–{hi}"
        game_max = self.maxes.get(s, 0)
        if c >= game_max:  # au-dela du max du jeu : c'est un over, il faut du puits
            need = r[1] * weight(s)
            if self.puits < need:
                g = self._generator(exclude=s, need=need - self.puits)
                if g:
                    return (f"{g[1][0]} sur {g[0]}",
                            f"{s} : {c}, tu vises {rng} (au-dessus du max du jeu {game_max}). "
                            f"Il faut {need:g} de reliquat, tu as {self.puits:g} : génère-en sur {g[0]}.")
            return (f"{r[0]} (+{r[1]}) sur {s}",
                    f"Over : {s} à {c}, tu vises {rng}. Reliquat {self.puits:g} / {need:g} nécessaire.")
        return (f"{r[0]} (+{r[1]}) sur {s}",
                f"{s} : {c}, tu vises {rng} (il manque {lo - c}).")

    def _generator(self, exclude=None, need=None):
        c = [(s, v, m) for s, v, m in self._lines() if v >= m > 0 and s != exclude and s not in EXO_STATS]
        if not c:
            return None
        opts = [(st, r, r[1] * weight(st)) for st, _, _ in c for r in runes(st)]
        if need is not None:  # la plus petite rune qui suffit a creer le reliquat manquant
            ok = [o for o in opts if o[2] >= need]
            if ok:
                return min(ok, key=lambda o: o[2])
        return max(opts, key=lambda o: o[2])

    def rune_of(self, advice):
        """Retrouve (stat, rune) à partir du texte du conseil."""
        txt = advice.split(" (")[0] if " sur " not in advice else advice
        if " sur " in advice:
            name, st = advice.split(" sur ", 1)
            name = name.split(" (")[0].strip()
        else:
            name, st = txt.strip(), None
            for k in EXO_STATS:
                if any(r[0] == name for r in runes(k)):
                    st = k
        if st not in STATS:
            return None
        for r in runes(st):
            if r[0] == name:
                return st, r
        return None

    def advise(self):
        a = self._advise()
        self.last_advice = a[0]
        sr = self.rune_of(a[0])
        self.last_chances = chances(self.values, self.maxes, sr[0], sr[1], self.level, self.mins) if sr else None
        return a

    def _advise(self):
        if not self.values:
            return ("En attente…", "Ouvre la fenêtre de FM avec ton objet, je lis les stats.")
        P = self.puits
        if self.goal.startswith("exo-"):
            s = self.goal[4:]
            w = weight(s)
            rn = runes(s)[0][0]
            if self.values.get(s, 0) >= 1 and self.maxes.get(s, 0) == 0:
                j = self._advise_jet(exclude=s)
                if not j:
                    return ("✅ Terminé !", f"Exo {s} passé et tout est au max. Ne repasse plus de rune.")
                return (j[0], j[1] + f" Exo {s} acquis : petites runes seulement, l'exo peut sauter.")
            if P >= w:
                return (f"{rn} (exo {s})", f"Reliquat {P:g} ≥ {w:g} : passe l'exo maintenant.")
            g = self._generator(need=w - P)
            if g:
                return (f"{g[1][0]} sur {g[0]}",
                        f"Il faut {w:g} de reliquat, tu as {P:g}. {g[0]} est au max : la rune (poids {g[2]:g}) va surtout échouer et remplir le reliquat.")
            return (f"{rn} (spam)", f"Il manque {w - P:g} de reliquat. Les échecs de la rune {rn} en créent.")
        if self.goal == "over" and self.over_stat in STATS:
            s, T = self.over_stat, self.over_target
            c, m = self.values.get(s, 0), self.maxes.get(s, 0)
            if T <= m:
                if m <= 0 and c <= 0:
                    return ("Indique la valeur visée", f"{s} n'est pas sur l'objet : tape la valeur voulue dans la case « viser » (ex. 1).")
                return ("Valeur visée trop basse", f"Pour un over sur {s}, vise plus que {m} (le max du jeu).")
            if c < m:
                r = best_rune(s, m - c)
                return (f"{r[0]} (+{r[1]}) sur {s}", f"Monte d'abord {s} au max ({c}/{m}).")
            if c >= T:
                j = self._advise_jet(exclude=s)
                return j or ("✅ Over atteint !", f"{s} = {c}. Arrête-toi là.")
            r = best_rune(s, T - c)
            need = r[1] * weight(s)
            if P >= need:
                return (f"{r[0]} (+{r[1]}) sur {s}", f"Reliquat {P:g} ≥ {need:g} : tente l'over.")
            g = self._generator(exclude=s, need=need - P)
            if g:
                return (f"{g[1][0]} sur {g[0]}", f"Il faut {need:g} de reliquat, tu as {P:g}. Génère-en sur {g[0]} (au max).")
            return (f"{r[0]} sur {s}", "Pas assez de reliquat : un échec en créera.")
        j = self._advise_jet()
        return j or ("✅ Jet terminé !", "Toutes les lignes sont dans tes fourchettes. Arrête-toi là.")
