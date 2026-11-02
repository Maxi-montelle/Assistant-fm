"""Mise à jour automatique depuis les « releases » GitHub du projet.

Au démarrage, l'application demande à GitHub quelle est la dernière version publiée.
Si elle est plus récente, un bouton propose de la télécharger et de l'installer.

Installation (version .exe) : Windows permet de RENOMMER un exe en cours d'exécution.
On renomme donc l'exe actuel en « .old », on met le nouveau à sa place et on le lance.
L'ancien fichier est supprimé au démarrage suivant. Pas de script .bat, pas d'attente.
"""
import json
import os
import subprocess
import sys
import urllib.request
import webbrowser

from version import VERSION, GITHUB_REPO

ASSET_NAME = "AssistantFM.exe"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"


def _parse(v):
    return tuple(int(x) for x in v.lstrip("vV").split(".") if x.isdigit())


def check_latest(timeout=5):
    """Renvoie (version, url_du_exe, notes) si une version plus récente existe, sinon None."""
    if not GITHUB_REPO or "/" not in GITHUB_REPO:
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "AssistantFM"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    tag = data.get("tag_name", "")
    if not tag or _parse(tag) <= _parse(VERSION):
        return None
    url = next((a["browser_download_url"] for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if not url:
        return None
    return tag.lstrip("vV"), url, (data.get("body") or "").strip()


def is_frozen():
    return getattr(sys, "frozen", False)


def cleanup_old(wait=0):
    """Au démarrage : supprime l'ancien exe laissé par la mise à jour précédente.
    `wait` : secondes pendant lesquelles on réessaie (l'ancien exe met un instant à se fermer)."""
    if not is_frozen():
        return
    import time
    end = time.time() + wait
    for p in (sys.executable + ".old", sys.executable + ".new"):
        while os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                if time.time() >= end:
                    break
                time.sleep(0.5)


def _download(url, dest, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "AssistantFM"})
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    if total and os.path.getsize(tmp) != total:
        os.remove(tmp)
        raise IOError("téléchargement incomplet, réessaie")
    os.replace(tmp, dest)


def _clean_env():
    """Environnement pour lancer le NOUVEL exe comme un programme indépendant.
    Sans ça, il réutiliserait le dossier temporaire de l'ancien (en cours d'effacement) et planterait."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_MEI", "_PYI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    mei = getattr(sys, "_MEIPASS", None)
    if mei:  # variables qui pointent vers le dossier temporaire de l'ancien exe (Tesseract, Tcl/Tk…)
        env = {k: v for k, v in env.items() if mei.lower() not in v.lower()}
    return env


def _downloads_dir():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def install(url, progress=None, args=()):
    """Télécharge et installe la nouvelle version.
    Renvoie "restart" si la nouvelle version est lancée (fermer l'application),
    ou un message à afficher si l'installation doit être finie à la main."""
    if not is_frozen():
        # version Python (lancer.bat) : on ouvre la page de téléchargement
        webbrowser.open(RELEASES_URL)
        return "Page de téléchargement ouverte : prends AssistantFM.exe."
    exe = sys.executable
    new, old = exe + ".new", exe + ".old"
    try:
        _download(url, new, progress)
    except PermissionError:
        # dossier protégé (Program Files…) : on dépose le nouvel exe dans Téléchargements
        dest = os.path.join(_downloads_dir(), ASSET_NAME)
        _download(url, dest, progress)
        subprocess.Popen(["explorer", "/select,", dest])
        return f"Nouvelle version enregistrée dans {dest} : ferme l'assistant et lance-la."
    try:
        if os.path.exists(old):
            os.remove(old)
        os.replace(exe, old)          # autorisé même si l'exe tourne
        try:
            os.replace(new, exe)
        except OSError:
            os.replace(old, exe)      # on remet l'ancien en place
            raise
    except OSError as ex:
        raise RuntimeError(f"remplacement de l'exe impossible ({ex}). "
                           f"Le nouvel exe est ici : {new}") from ex
    subprocess.Popen([exe, *args], env=_clean_env(), cwd=os.path.dirname(exe),
                     close_fds=True, creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_PROCESS_GROUP
    return "restart"
