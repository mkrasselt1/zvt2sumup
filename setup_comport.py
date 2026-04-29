"""
Virtuellen COM-Port einrichten (com0com).

Erkennt ob com0com installiert ist, erstellt Port-Paare und
prueft die Verbindung. Wird von setup_comport.bat aufgerufen.
"""

import subprocess
import os
import sys
import winreg
import glob


def find_com0com_setupc() -> str:
    """Sucht die com0com setupc.exe auf dem System."""
    # 1. Registry-Eintrag pruefen
    for reg_path in [
        r"SOFTWARE\com0com",
        r"SOFTWARE\WOW6432Node\com0com",
    ]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                install_dir = winreg.QueryValueEx(key, "Install_Dir")[0]
                setupc = os.path.join(install_dir, "setupc.exe")
                if os.path.exists(setupc):
                    return setupc
        except (FileNotFoundError, OSError):
            pass

    # 2. Bekannte Installationspfade
    search_paths = [
        r"C:\Program Files\com0com\setupc.exe",
        r"C:\Program Files (x86)\com0com\setupc.exe",
        r"C:\com0com\setupc.exe",
    ]

    # Auch in Programme-Ordnern suchen
    for pf in [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]:
        if pf:
            for d in glob.glob(os.path.join(pf, "com0com*")):
                search_paths.append(os.path.join(d, "setupc.exe"))

    for path in search_paths:
        if os.path.exists(path):
            return path

    # 3. Im PATH suchen
    try:
        result = subprocess.run(["where", "setupc.exe"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass

    return ""


def find_com0com_installer() -> str:
    """Sucht eine com0com-Installationsdatei im Projektverzeichnis."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    drivers_dir = os.path.join(project_dir, "drivers")

    patterns = [
        os.path.join(drivers_dir, "com0com*setup*.exe"),
        os.path.join(drivers_dir, "com0com*.exe"),
        os.path.join(drivers_dir, "setup*.exe"),
        os.path.join(project_dir, "com0com*setup*.exe"),
    ]

    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]

    return ""


def download_com0com() -> str:
    """Laedt com0com (signierte Version) herunter."""
    import urllib.request
    import zipfile

    project_dir = os.path.dirname(os.path.abspath(__file__))
    drivers_dir = os.path.join(project_dir, "drivers")
    os.makedirs(drivers_dir, exist_ok=True)

    # com0com signed driver von GitHub
    url = "https://github.com/pauloricardoferreira/com0com-signed-drivers/releases/download/v3.0.0.0/com0com-3.0.0.0-i386-and-amd64-signed.zip"
    zip_path = os.path.join(drivers_dir, "com0com-signed.zip")
    extract_dir = os.path.join(drivers_dir, "com0com")

    print(f"\n  Lade com0com (signierte Version) herunter...")
    print(f"  URL: {url}")

    try:
        urllib.request.urlretrieve(url, zip_path)
        print(f"  Download abgeschlossen.")

        # Entpacken
        print(f"  Entpacke nach {extract_dir}...")
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)

        os.remove(zip_path)

        # Setup.exe suchen
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f.lower().startswith("setup") and f.lower().endswith(".exe"):
                    return os.path.join(root, f)

        # Fallback: irgendeine exe
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f.lower().endswith(".exe"):
                    return os.path.join(root, f)

        print("  WARNUNG: Keine Setup.exe im Archiv gefunden.")
        print(f"  Bitte manuell installieren aus: {extract_dir}")
        return ""

    except Exception as e:
        print(f"  FEHLER beim Download: {e}")
        print()
        print("  Bitte manuell herunterladen von:")
        print("  https://github.com/pauloricardoferreira/com0com-signed-drivers")
        print(f"  und nach {drivers_dir} kopieren.")
        return ""


def list_existing_pairs(setupc: str) -> list:
    """Listet vorhandene com0com Port-Paare auf."""
    pairs = []
    try:
        result = subprocess.run(
            [setupc, "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line and "CNCA" in line or "CNCB" in line:
                    pairs.append(line)
    except Exception:
        pass
    return pairs


def get_com_ports_in_use() -> list:
    """Gibt eine Liste aller belegten COM-Ports zurueck."""
    ports = []
    try:
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            ports.append(port.device)
    except ImportError:
        # Fallback: Registry lesen
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                i = 0
                while True:
                    try:
                        _, value, _ = winreg.EnumValue(key, i)
                        ports.append(value)
                        i += 1
                    except OSError:
                        break
        except OSError:
            pass
    return sorted(ports)


def find_free_port_pair(used_ports: list) -> tuple:
    """Findet ein freies COM-Port-Paar."""
    for base in range(3, 50, 2):
        port_a = f"COM{base}"
        port_b = f"COM{base + 1}"
        if port_a not in used_ports and port_b not in used_ports:
            return port_a, port_b
    return "COM3", "COM4"


def create_port_pair(setupc: str, port_kasse: str, port_gateway: str) -> bool:
    """Erstellt ein com0com Port-Paar."""
    # Port-Nummern extrahieren
    num_a = port_kasse.replace("COM", "")
    num_b = port_gateway.replace("COM", "")

    print(f"\n  Erstelle Port-Paar: {port_kasse} <-> {port_gateway}")
    print(f"    {port_kasse} = fuer das Kassensystem")
    print(f"    {port_gateway} = fuer das Gateway")

    try:
        # Neues Paar installieren mit festen Port-Namen
        cmd = [setupc, "install", "PortName=COM" + num_a, "PortName=COM" + num_b]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode == 0:
            print(f"\n  Port-Paar erfolgreich erstellt!")
            return True
        else:
            print(f"\n  FEHLER beim Erstellen:")
            if result.stdout.strip():
                print(f"    {result.stdout.strip()}")
            if result.stderr.strip():
                print(f"    {result.stderr.strip()}")

            # Moeglicherweise braucht es Admin-Rechte
            print("\n  Hinweis: com0com benoetigt Administrator-Rechte!")
            print("  Bitte dieses Skript als Administrator ausfuehren.")
            return False

    except subprocess.TimeoutExpired:
        print("  FEHLER: Timeout bei der Port-Erstellung.")
        return False
    except Exception as e:
        print(f"  FEHLER: {e}")
        return False


def update_config(port_gateway: str):
    """Aktualisiert die config.ini mit dem Gateway-Port."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gateway.config import GatewayConfig

    config = GatewayConfig()
    config.set("gateway", "modus", "com")
    config.set("gateway", "com_port", port_gateway)
    config.save()
    print(f"\n  config.ini aktualisiert:")
    print(f"    modus = com")
    print(f"    com_port = {port_gateway}")


def main():
    print()
    print("=" * 55)
    print("  Virtuellen COM-Port einrichten (com0com)")
    print("=" * 55)
    print()
    print("  Fuer den COM-Port-Modus braucht das Gateway ein")
    print("  virtuelles Port-Paar: ein Port fuer die Kasse,")
    print("  ein Port fuer das Gateway.")
    print()

    # 1. com0com suchen
    print("  [1/4] Suche com0com...")
    setupc = find_com0com_setupc()

    if setupc:
        print(f"    Gefunden: {setupc}")
    else:
        print("    com0com ist NICHT installiert.")
        print()

        # Pruefen ob Installer im Projektverzeichnis liegt
        installer = find_com0com_installer()
        if not installer:
            print()
            print("  com0com kann automatisch heruntergeladen werden.")
            print("    1) Automatisch herunterladen und installieren")
            print("    2) Ich installiere es selbst")
            choice = input("\n  Auswahl [1/2]: ").strip()

            if choice == "1":
                installer = download_com0com()
            else:
                print()
                print("  Bitte installieren Sie com0com:")
                print("    https://sourceforge.net/projects/com0com/")
                print("    Fuer Windows 10/11 (signiert):")
                print("    https://github.com/pauloricardoferreira/com0com-signed-drivers")
                print()
                input("  Druecken Sie Enter nach der Installation...")
                setupc = find_com0com_setupc()
                if not setupc:
                    print("  com0com wurde nicht gefunden. Abbruch.")
                    return

        if installer and not setupc:
            print(f"\n  Installer: {os.path.basename(installer)}")
            print("  Starte Installation...")
            print("  Bitte folgen Sie dem Installationsassistenten.")
            print("  WICHTIG: Standardpfad beibehalten!\n")
            subprocess.run([installer], timeout=300)

            # Nochmal suchen
            setupc = find_com0com_setupc()
            if not setupc:
                print("\n  com0com wurde nicht gefunden nach Installation.")
                print("  Bitte starten Sie dieses Skript erneut.")
                return

    # 2. Vorhandene Ports pruefen
    print("\n  [2/4] Pruefe vorhandene COM-Ports...")
    used_ports = get_com_ports_in_use()
    if used_ports:
        print(f"    Belegte Ports: {', '.join(used_ports)}")
    else:
        print("    Keine COM-Ports belegt.")

    existing = list_existing_pairs(setupc)
    if existing:
        print(f"\n    Vorhandene com0com-Paare:")
        for line in existing:
            print(f"      {line}")

    # 3. Port-Paar erstellen oder vorhandenes nutzen
    print("\n  [3/4] Port-Paar einrichten...")
    port_kasse, port_gateway = find_free_port_pair(used_ports)

    print(f"\n    Vorgeschlagenes Port-Paar:")
    print(f"      {port_kasse} = Kassensystem (POS)")
    print(f"      {port_gateway} = Gateway")

    print()
    print("  Optionen:")
    print(f"    1) Vorgeschlagenes Paar verwenden ({port_kasse} <-> {port_gateway})")
    print("    2) Eigene Port-Nummern eingeben")
    if existing:
        print("    3) Vorhandenes Paar verwenden (nur Config anpassen)")

    choice = input("\n  Auswahl: ").strip()

    if choice == "2":
        port_kasse = input("  Port fuer Kasse (z.B. COM3): ").strip().upper()
        port_gateway = input("  Port fuer Gateway (z.B. COM4): ").strip().upper()
        if not port_kasse.startswith("COM") or not port_gateway.startswith("COM"):
            print("  Ungueltige Port-Namen! Format: COMx")
            return
    elif choice == "3" and existing:
        port_gateway = input("  Gateway-Port eingeben (z.B. COM4): ").strip().upper()
        print(f"\n  Verwende vorhandenen Port: {port_gateway}")
        update_config(port_gateway)
        print("\n  Fertig!")
        return
    elif choice != "1":
        print("  Ungueltige Auswahl.")
        return

    # Port-Paar erstellen
    if create_port_pair(setupc, port_kasse, port_gateway):
        # 4. Config aktualisieren
        print("\n  [4/4] Konfiguration aktualisieren...")
        update_config(port_gateway)

        print()
        print("=" * 55)
        print("  Einrichtung abgeschlossen!")
        print("=" * 55)
        print()
        print(f"  Kassensystem:  {port_kasse}")
        print(f"  Gateway:       {port_gateway}")
        print()
        print(f"  Stellen Sie im Kassensystem {port_kasse}")
        print(f"  als ZVT-Port ein (Baudrate: 9600).")
        print()
        print("  Das Gateway ist bereits konfiguriert.")
        print("  Starten Sie es mit: start.bat")
    else:
        print("\n  Port-Paar konnte nicht erstellt werden.")
        print("  Bitte als Administrator ausfuehren oder")
        print("  com0com manuell konfigurieren.")

    print()
    input("  Druecken Sie Enter zum Beenden...")


if __name__ == "__main__":
    main()
