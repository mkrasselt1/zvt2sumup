"""
Updater fuer das ZVT-zu-SumUp Gateway.

Prueft auf neue Versionen und aktualisiert automatisch.
Unterstuetzt:
- Git-basiertes Update (wenn git installiert ist)
- ZIP-Download von GitHub (Fallback ohne git)
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile
import zipfile
import logging
from datetime import datetime

import requests

logger = logging.getLogger("zvt2sumup.updater")

# Projektverzeichnis
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# GitHub-Repository (anpassen wenn das Repo woanders liegt)
GITHUB_OWNER = "mkrasselt1"
GITHUB_REPO = "zvt2sumup"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"

# Lokale Versionsdatei
VERSION_FILE = os.path.join(PROJECT_DIR, "version.json")


def get_local_version() -> dict:
    """Liest die lokale Versionsinformation."""
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Fallback: Version aus __init__.py
    from gateway import __version__
    return {
        "version": __version__,
        "updated": "unbekannt",
    }


def save_local_version(version: str, method: str):
    """Speichert die aktuelle Version."""
    data = {
        "version": version,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": method,
    }
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logger.warning(f"Konnte Versionsdatei nicht speichern: {e}")


def has_git() -> bool:
    """Prueft ob git verfuegbar ist."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_git_repo() -> bool:
    """Prueft ob das Projektverzeichnis ein Git-Repository ist."""
    return os.path.isdir(os.path.join(PROJECT_DIR, ".git"))


def check_for_updates() -> dict:
    """
    Prueft ob ein Update verfuegbar ist.

    Returns:
        Dict mit:
        - available: True/False
        - local_version: Aktuelle lokale Version
        - remote_version: Neueste verfuegbare Version
        - release_notes: Aenderungen (wenn verfuegbar)
        - download_url: URL zum Download
        - error: Fehlermeldung (wenn Pruefung fehlschlug)
    """
    result = {
        "available": False,
        "local_version": get_local_version().get("version", "unbekannt"),
    }

    # Methode 1: Git
    if has_git() and is_git_repo():
        return _check_git_updates(result)

    # Methode 2: GitHub API
    return _check_github_updates(result)


def _check_git_updates(result: dict) -> dict:
    """Prueft auf Updates via git."""
    try:
        # Remote aktualisieren
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=30,
        )

        # Lokalen und Remote-Stand vergleichen
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=5,
        ).stdout.strip()

        remote = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=5,
        ).stdout.strip()

        if not remote:
            # Vielleicht heisst der Branch "master"
            remote = subprocess.run(
                ["git", "rev-parse", "origin/master"],
                cwd=PROJECT_DIR, capture_output=True, text=True, timeout=5,
            ).stdout.strip()

        if local and remote and local != remote:
            # Aenderungen auflisten
            log = subprocess.run(
                ["git", "log", "--oneline", f"{local}..{remote}"],
                cwd=PROJECT_DIR, capture_output=True, text=True, timeout=10,
            ).stdout.strip()

            result["available"] = True
            result["remote_version"] = remote[:8]
            result["release_notes"] = log or "Aenderungen verfuegbar"
            result["method"] = "git"
            logger.info(f"Update verfuegbar: {local[:8]} -> {remote[:8]}")
        else:
            result["remote_version"] = local[:8] if local else "unbekannt"
            logger.info("Kein Update verfuegbar (git)")

    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        result["error"] = f"Git-Fehler: {e}"
        logger.warning(f"Git-Update-Pruefung fehlgeschlagen: {e}")

    return result


def _check_github_updates(result: dict) -> dict:
    """Prueft auf Updates via GitHub Releases API."""
    try:
        resp = requests.get(
            f"{GITHUB_API}/releases/latest",
            timeout=10,
            headers={"Accept": "application/vnd.github.v3+json"},
        )

        if resp.status_code == 200:
            release = resp.json()
            remote_version = release.get("tag_name", "").lstrip("v")
            local_version = result["local_version"]

            result["remote_version"] = remote_version
            result["release_notes"] = release.get("body", "")
            result["html_url"] = release.get("html_url", "")

            # ZIP-Download URL
            assets = release.get("assets", [])
            for asset in assets:
                if asset["name"].endswith(".zip"):
                    result["download_url"] = asset["browser_download_url"]
                    break
            else:
                # Fallback: Source-Code ZIP
                result["download_url"] = release.get("zipball_url", "")

            if remote_version and remote_version != local_version:
                result["available"] = True
                result["method"] = "github"
                logger.info(f"Update verfuegbar: {local_version} -> {remote_version}")
            else:
                logger.info("Kein Update verfuegbar (GitHub)")

        elif resp.status_code == 404:
            # Kein Release vorhanden - nach Commits schauen
            result["error"] = "Kein Release auf GitHub gefunden"
            logger.info("Kein GitHub-Release gefunden")
        else:
            result["error"] = f"GitHub-API-Fehler: {resp.status_code}"

    except requests.RequestException as e:
        result["error"] = f"Netzwerkfehler: {e}"
        logger.warning(f"GitHub-Update-Pruefung fehlgeschlagen: {e}")

    return result


def perform_update() -> dict:
    """
    Fuehrt das Update durch.

    Returns:
        Dict mit:
        - success: True/False
        - message: Statusmeldung
        - backup_path: Pfad zum Backup (wenn erstellt)
    """
    result = {"success": False}

    # Methode 1: Git pull
    if has_git() and is_git_repo():
        return _update_via_git(result)

    # Methode 2: GitHub ZIP
    return _update_via_zip(result)


def _update_via_git(result: dict) -> dict:
    """Update via git pull."""
    logger.info("Starte Update via git pull...")

    try:
        # Lokale Aenderungen pruefen
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=10,
        ).stdout.strip()

        if status:
            # Lokale Aenderungen vorhanden - config.ini schuetzen
            logger.info("Lokale Aenderungen erkannt, sichere config.ini...")
            subprocess.run(
                ["git", "stash", "push", "-m", "update-backup"],
                cwd=PROJECT_DIR, capture_output=True, text=True, timeout=10,
            )

        # Pull ausfuehren
        pull = subprocess.run(
            ["git", "pull", "origin"],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=60,
        )

        if pull.returncode == 0:
            # Gestashte Aenderungen wiederherstellen
            if status:
                subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=PROJECT_DIR, capture_output=True, text=True, timeout=10,
                )

            # Abhaengigkeiten aktualisieren
            _update_dependencies()

            # Version speichern
            head = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=PROJECT_DIR, capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            save_local_version(head, "git")

            result["success"] = True
            result["message"] = f"Update erfolgreich (git: {head})"
            logger.info(result["message"])
        else:
            result["message"] = f"Git pull fehlgeschlagen:\n{pull.stderr}"
            logger.error(result["message"])

    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        result["message"] = f"Git-Fehler: {e}"
        logger.error(result["message"])

    return result


def _update_via_zip(result: dict) -> dict:
    """Update via GitHub ZIP-Download."""
    logger.info("Starte Update via ZIP-Download...")

    update_info = check_for_updates()
    download_url = update_info.get("download_url")
    if not download_url:
        result["message"] = "Kein Download-Link verfuegbar"
        return result

    try:
        # 1. Backup erstellen
        backup_dir = os.path.join(PROJECT_DIR, "_backup")
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)

        # Wichtige Dateien sichern
        files_to_backup = ["config.ini", "version.json", "zvt2sumup.log"]
        os.makedirs(backup_dir, exist_ok=True)
        for fname in files_to_backup:
            fpath = os.path.join(PROJECT_DIR, fname)
            if os.path.exists(fpath):
                shutil.copy2(fpath, os.path.join(backup_dir, fname))

        result["backup_path"] = backup_dir
        logger.info(f"Backup erstellt: {backup_dir}")

        # 2. ZIP herunterladen
        logger.info(f"Lade herunter: {download_url}")
        resp = requests.get(download_url, timeout=60, stream=True)
        resp.raise_for_status()

        tmp_zip = os.path.join(tempfile.gettempdir(), "zvt2sumup_update.zip")
        with open(tmp_zip, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # 3. ZIP entpacken
        tmp_extract = os.path.join(tempfile.gettempdir(), "zvt2sumup_extract")
        if os.path.exists(tmp_extract):
            shutil.rmtree(tmp_extract)

        with zipfile.ZipFile(tmp_zip, "r") as zf:
            zf.extractall(tmp_extract)

        # GitHub ZIPs haben einen Ordner auf oberster Ebene
        extracted_dirs = os.listdir(tmp_extract)
        if len(extracted_dirs) == 1:
            source_dir = os.path.join(tmp_extract, extracted_dirs[0])
        else:
            source_dir = tmp_extract

        # 4. Gateway-Dateien aktualisieren (config.ini etc. nicht ueberschreiben)
        protected = {"config.ini", "version.json", "zvt2sumup.log", "_backup"}
        for item in os.listdir(source_dir):
            if item in protected or item.startswith("."):
                continue
            src = os.path.join(source_dir, item)
            dst = os.path.join(PROJECT_DIR, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        # 5. Aufraeumen
        os.remove(tmp_zip)
        shutil.rmtree(tmp_extract)

        # 6. Abhaengigkeiten aktualisieren
        _update_dependencies()

        # 7. Version speichern
        remote_ver = update_info.get("remote_version", "unbekannt")
        save_local_version(remote_ver, "zip")

        result["success"] = True
        result["message"] = f"Update erfolgreich (Version: {remote_ver})"
        logger.info(result["message"])

    except requests.RequestException as e:
        result["message"] = f"Download-Fehler: {e}"
        logger.error(result["message"])
    except (zipfile.BadZipFile, OSError) as e:
        result["message"] = f"Entpack-Fehler: {e}"
        logger.error(result["message"])

    return result


def _update_dependencies():
    """Aktualisiert Python-Abhaengigkeiten nach einem Update."""
    req_file = os.path.join(PROJECT_DIR, "requirements.txt")
    if os.path.exists(req_file):
        logger.info("Aktualisiere Abhaengigkeiten...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
                cwd=PROJECT_DIR, capture_output=True, text=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Abhaengigkeiten konnten nicht aktualisiert werden: {e}")


def main():
    """Kommandozeilen-Updater."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        datefmt="%H:%M:%S",
    )

    print()
    print("=" * 50)
    print("  ZVT-zu-SumUp Gateway - Updater")
    print("=" * 50)
    print()

    local = get_local_version()
    print(f"  Aktuelle Version: {local.get('version', '?')}")
    print(f"  Letztes Update:   {local.get('updated', '?')}")
    if has_git() and is_git_repo():
        print(f"  Update-Methode:   Git")
    else:
        print(f"  Update-Methode:   GitHub-Download")
    print()

    print("Pruefe auf Updates...")
    info = check_for_updates()

    if info.get("error"):
        print(f"\n  Fehler: {info['error']}")
        if not info["available"]:
            print()
            input("Druecken Sie Enter zum Beenden...")
            return

    if not info["available"]:
        print("\n  Kein Update verfuegbar - Sie nutzen die neueste Version.")
        print()
        input("Druecken Sie Enter zum Beenden...")
        return

    print(f"\n  Neue Version verfuegbar: {info.get('remote_version', '?')}")
    if info.get("release_notes"):
        print(f"\n  Aenderungen:")
        for line in info["release_notes"].splitlines()[:10]:
            print(f"    {line}")
    print()

    answer = input("  Jetzt aktualisieren? (j/n): ").strip().lower()
    if answer not in ("j", "ja", "y", "yes"):
        print("\n  Update abgebrochen.")
        input("Druecken Sie Enter zum Beenden...")
        return

    print("\nUpdate wird durchgefuehrt...")
    result = perform_update()

    if result["success"]:
        print(f"\n  {result['message']}")
        print()
        print("  WICHTIG: Bitte starten Sie das Gateway neu,")
        print("  damit die Aenderungen wirksam werden.")
        if result.get("backup_path"):
            print(f"\n  Backup: {result['backup_path']}")
    else:
        print(f"\n  FEHLER: {result['message']}")
        if result.get("backup_path"):
            print(f"  Backup verfuegbar: {result['backup_path']}")

    print()
    input("Druecken Sie Enter zum Beenden...")


if __name__ == "__main__":
    main()
