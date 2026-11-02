"""Mise à jour automatique depuis les « releases » GitHub du projet.

Au démarrage, l'application demande à GitHub quelle est la dernière version publiée.
Si elle est plus récente, un bouton propose de la télécharger et de l'installer.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from version import VERSION, GITHUB_REPO

ASSET_NAME = "AssistantFM.exe"


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


def install(url, progress=None):
    """Télécharge le nouvel exe, puis lance un petit script qui remplace l'ancien
    une fois l'application fermée, et la relance. Ne marche que pour la version .exe."""
    if not is_frozen():
        raise RuntimeError("La mise à jour automatique ne marche que dans la version .exe.")
    exe = sys.executable
    new = exe + ".new"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AssistantFM"}), timeout=60) as r, \
            open(new, "wb") as f:
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
    bat = os.path.join(tempfile.gettempdir(), "assistantfm_update.bat")
    with open(bat, "w", encoding="utf-8") as f:
        f.write(f"""@echo off
chcp 65001 >nul
:wait
timeout /t 1 /nobreak >nul
del "{exe}" >nul 2>&1
if exist "{exe}" goto wait
move /y "{new}" "{exe}" >nul
start "" "{exe}"
del "%~f0"
""")
    subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)  # CREATE_NO_WINDOW
