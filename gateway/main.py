"""
ZVT-zu-SumUp Gateway - Hauptprogramm.

Startet den ZVT-Server (TCP oder COM) und verbindet ihn
mit der SumUp Cloud-API.

Kann sowohl interaktiv (start.bat) als auch als Windows-Dienst
(dienst_install.bat) betrieben werden.
"""

import sys
import os
import signal
import logging
import time
import threading

# Projektverzeichnis zum Pfad hinzufuegen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gateway.config import GatewayConfig
from gateway.sumup_api import SumUpClient
from gateway.handler import ZVTGatewayHandler
from gateway.server import ZVTTCPServer, ZVTSerialServer


def setup_logging(config: GatewayConfig):
    """Richtet das Logging ein."""
    log_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_file = os.path.join(log_dir, config.log_datei)

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


class GatewayApp:
    """
    Zentrale Gateway-Anwendung.

    Kann sowohl interaktiv als auch vom Windows-Dienst
    gestartet und gestoppt werden.
    """

    def __init__(self):
        self.server = None
        self.config = None
        self.logger = None
        self._stop_event = threading.Event()

    def start(self):
        """Startet das Gateway (blockiert NICHT)."""
        self.config = GatewayConfig()
        setup_logging(self.config)
        self.logger = logging.getLogger("zvt2sumup")

        # Konfiguration validieren
        errors = self.config.validate()
        if errors:
            for err in errors:
                self.logger.error(f"Konfigurationsfehler: {err}")
            raise RuntimeError("Konfiguration ungueltig: " + "; ".join(errors))

        self.logger.info("Konfiguration geladen")
        self.logger.info(f"Modus: {self.config.modus.upper()}")

        # SumUp-Client erstellen
        terminal_id = self.config.terminal_id or None
        sumup = SumUpClient(
            api_key=self.config.api_key,
            merchant_code=self.config.merchant_code,
            terminal_id=terminal_id,
            affiliate_key=self.config.affiliate_key,
            affiliate_app_id=self.config.affiliate_app_id,
        )

        # Verbindung pruefen und Merchant Code automatisch ermitteln
        conn = sumup.test_connection()
        if not conn["ok"]:
            self.logger.warning(f"SumUp-Verbindung fehlgeschlagen: {conn.get('error', '?')} - Gateway startet trotzdem")
        else:
            mc = conn.get("merchant_code", "")
            if mc:
                self.logger.info(f"Merchant Code: {mc}")

        # Terminal-ID automatisch erkennen wenn nicht gesetzt
        if not terminal_id:
            self.logger.info("Keine Terminal-ID konfiguriert - suche automatisch...")
            terminals = sumup.get_terminals()
            if len(terminals) == 1:
                tid = terminals[0].get("id", terminals[0].get("terminal_id", ""))
                name = terminals[0].get("name", "Terminal")
                sumup.terminal_id = str(tid)
                self.logger.info(f"Terminal automatisch erkannt: {name} (ID: {tid})")
            elif len(terminals) > 1:
                self.logger.warning(
                    f"{len(terminals)} Terminals gefunden - bitte Terminal-ID "
                    f"in config.ini oder setup.bat festlegen!"
                )
            else:
                self.logger.warning("Kein Terminal gefunden - Zahlungen nicht moeglich")

        # Handler erstellen
        handler = ZVTGatewayHandler(
            sumup=sumup,
            currency=self.config.waehrung,
            payment_timeout=self.config.zahlung_timeout,
        )

        # Server starten
        if self.config.modus == "tcp":
            self.server = ZVTTCPServer(
                host=self.config.tcp_host,
                port=self.config.tcp_port,
                handler=handler.handle,
            )
            self.server.start()
            self.logger.info(f"Gateway laeuft (TCP {self.config.tcp_host}:{self.config.tcp_port})")

        elif self.config.modus == "com":
            self.server = ZVTSerialServer(
                port=self.config.com_port,
                baudrate=self.config.com_baudrate,
                handler=handler.handle,
            )
            self.server.start()
            self.logger.info(f"Gateway laeuft (COM {self.config.com_port})")

        else:
            raise RuntimeError(f"Unbekannter Modus: {self.config.modus}")

        self._stop_event.clear()

    def stop(self):
        """Stoppt das Gateway."""
        self._stop_event.set()
        if self.server:
            self.server.stop()
            self.server = None
        if self.logger:
            self.logger.info("Gateway gestoppt")

    def wait(self):
        """Blockiert bis stop() aufgerufen wird."""
        self._stop_event.wait()

    @property
    def is_running(self) -> bool:
        return self.server is not None and not self._stop_event.is_set()


def print_banner():
    """Zeigt das Start-Banner an."""
    print()
    print("=" * 56)
    print("  ZVT-zu-SumUp Gateway v1.0")
    print("  Verbindet ZVT-Kassen mit SumUp Solo Terminals")
    print("=" * 56)
    print()


def main():
    """Interaktiver Start (Konsole / start.bat)."""
    print_banner()

    app = GatewayApp()

    try:
        app.start()
    except RuntimeError as e:
        print(f"FEHLER: {e}")
        print()
        print("Bitte config.ini bearbeiten oder setup.bat ausfuehren.")
        print()
        input("Druecken Sie Enter zum Beenden...")
        sys.exit(1)

    config = app.config
    if config.modus == "tcp":
        print(f"Gateway laeuft! (TCP {config.tcp_host}:{config.tcp_port})")
        print()
        print("Kassensystem-Einstellung:")
        print(f"  IP:   {config.tcp_host}")
        print(f"  Port: {config.tcp_port}")
    elif config.modus == "com":
        print(f"Gateway laeuft! (COM-Port {config.com_port})")
        print()
        print("Kassensystem-Einstellung:")
        print(f"  COM-Port: {config.com_port}")
        print(f"  Baudrate: {config.com_baudrate}")

    print()
    print("-" * 56)
    print("  Druecken Sie Strg+C zum Beenden")
    print("-" * 56)
    print()

    # Signal-Handler fuer sauberes Beenden
    def signal_handler(sig, frame):
        print("\nBeende Gateway...")
        app.stop()

    signal.signal(signal.SIGINT, signal_handler)

    try:
        while app.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBeende Gateway...")
    finally:
        app.stop()


if __name__ == "__main__":
    main()
