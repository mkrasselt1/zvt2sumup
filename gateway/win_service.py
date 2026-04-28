"""
Windows-Dienst fuer das ZVT-zu-SumUp Gateway.

Ermoeglicht den Betrieb als Hintergrunddienst, der automatisch
mit Windows startet - ohne dass ein Benutzer angemeldet sein muss.

Installation:   python -m gateway.win_service install
Starten:         python -m gateway.win_service start
Stoppen:         python -m gateway.win_service stop
Deinstallation:  python -m gateway.win_service remove
Status:          python -m gateway.win_service status
"""

import sys
import os
import time
import logging

# Projektverzeichnis setzen (wichtig fuer den Dienst-Kontext)
SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVICE_DIR)
os.chdir(SERVICE_DIR)

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


SERVICE_NAME = "ZVT2SumUpGateway"
SERVICE_DISPLAY = "ZVT-zu-SumUp Gateway"
SERVICE_DESC = (
    "Gateway zwischen ZVT-Kassensystemen und SumUp Solo "
    "Cloud-Kartenterminals. Uebersetzt ZVT-Protokoll in "
    "SumUp API-Aufrufe."
)


if HAS_WIN32:
    class ZVTSumUpService(win32serviceutil.ServiceFramework):
        """Windows-Dienst-Klasse."""

        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESC

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.app = None

        def SvcStop(self):
            """Wird aufgerufen wenn der Dienst gestoppt wird."""
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)
            if self.app:
                self.app.stop()

        def SvcDoRun(self):
            """Hauptroutine des Dienstes."""
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )

            try:
                self._run()
            except Exception as e:
                servicemanager.LogErrorMsg(f"{self._svc_name_}: {e}")

        def _run(self):
            """Startet das Gateway im Dienst-Modus."""
            from gateway.main import GatewayApp, setup_logging
            from gateway.config import GatewayConfig

            # Logging nur in Datei (kein stdout im Dienst)
            config = GatewayConfig()
            log_file = os.path.join(SERVICE_DIR, config.log_datei)
            logging.basicConfig(
                level=getattr(logging, config.log_level, logging.INFO),
                format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                handlers=[
                    logging.FileHandler(log_file, encoding="utf-8"),
                ],
            )

            logger = logging.getLogger("zvt2sumup.service")
            logger.info("Windows-Dienst wird gestartet...")

            self.app = GatewayApp()

            try:
                self.app.start()
                logger.info("Gateway als Dienst gestartet")

                # Warten bis Stopp-Signal kommt
                while self.app.is_running:
                    rc = win32event.WaitForSingleObject(self.stop_event, 1000)
                    if rc == win32event.WAIT_OBJECT_0:
                        break

            except Exception as e:
                logger.error(f"Dienst-Fehler: {e}", exc_info=True)
            finally:
                if self.app:
                    self.app.stop()
                logger.info("Windows-Dienst beendet")


def print_status():
    """Zeigt den aktuellen Dienst-Status an."""
    if not HAS_WIN32:
        print("pywin32 nicht installiert!")
        return

    import win32service
    try:
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            svc = win32service.OpenService(scm, SERVICE_NAME, win32service.SERVICE_QUERY_STATUS)
            try:
                status = win32service.QueryServiceStatus(svc)
                state = status[1]
                states = {
                    win32service.SERVICE_STOPPED: "Gestoppt",
                    win32service.SERVICE_START_PENDING: "Wird gestartet...",
                    win32service.SERVICE_STOP_PENDING: "Wird gestoppt...",
                    win32service.SERVICE_RUNNING: "Laeuft",
                    win32service.SERVICE_CONTINUE_PENDING: "Wird fortgesetzt...",
                    win32service.SERVICE_PAUSE_PENDING: "Wird pausiert...",
                    win32service.SERVICE_PAUSED: "Pausiert",
                }
                print(f"Dienst '{SERVICE_DISPLAY}': {states.get(state, f'Unbekannt ({state})')}")
            finally:
                win32service.CloseServiceHandle(svc)
        except Exception:
            print(f"Dienst '{SERVICE_NAME}' ist nicht installiert.")
        finally:
            win32service.CloseServiceHandle(scm)
    except Exception as e:
        print(f"Fehler beim Abfragen: {e}")


def main():
    if not HAS_WIN32:
        print()
        print("FEHLER: pywin32 ist nicht installiert!")
        print()
        print("Bitte ausfuehren:")
        print("  pip install pywin32")
        print("  python -m pywin32_postinstall -install")
        print()
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print_status()
        return

    if len(sys.argv) == 1:
        # Ohne Argumente: Hilfe anzeigen
        print()
        print(f"  {SERVICE_DISPLAY} - Windows-Dienst")
        print("  " + "=" * 45)
        print()
        print("  Befehle:")
        print(f"    python -m gateway.win_service install   Dienst installieren")
        print(f"    python -m gateway.win_service start     Dienst starten")
        print(f"    python -m gateway.win_service stop      Dienst stoppen")
        print(f"    python -m gateway.win_service remove    Dienst deinstallieren")
        print(f"    python -m gateway.win_service status    Status anzeigen")
        print(f"    python -m gateway.win_service update    Dienst aktualisieren")
        print()
        print("  Oder verwenden Sie die Batch-Dateien:")
        print("    dienst_install.bat   - Installiert und startet den Dienst")
        print("    dienst_entfernen.bat - Stoppt und entfernt den Dienst")
        print()
        return

    win32serviceutil.HandleCommandLine(ZVTSumUpService)


if __name__ == "__main__":
    main()
