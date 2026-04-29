"""
Konfigurationsverwaltung fuer das ZVT-SumUp-Gateway.

Liest und schreibt die config.ini Datei.
"""

import os
import configparser
import logging

logger = logging.getLogger("zvt2sumup.config")

# Standard-Konfigurationsdatei
CONFIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.ini")

# Standardwerte
DEFAULTS = {
    "gateway": {
        "modus": "tcp",            # tcp oder com
        "tcp_port": "20007",       # ZVT Standard-Port
        "tcp_host": "127.0.0.1",   # Nur lokal
        "com_port": "COM3",        # Virtueller COM-Port
        "com_baudrate": "9600",    # ZVT Standard-Baudrate
        "waehrung": "EUR",
        "log_level": "INFO",
        "log_datei": "zvt2sumup.log",
    },
    "sumup": {
        "api_key": "",
        "merchant_code": "",
        "terminal_id": "",
        "affiliate_key": "",
        "affiliate_app_id": "",
        "zahlung_timeout": "120",  # Sekunden
    },
}


class GatewayConfig:
    """Verwaltet die Gateway-Konfiguration."""

    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self._load()

    def _load(self):
        """Laedt die Konfiguration oder erstellt Standardwerte."""
        # Zuerst Standardwerte setzen
        for section, values in DEFAULTS.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
            for key, default in values.items():
                self.config.set(section, key, default)

        # Dann vorhandene Datei laden (ueberschreibt Standards)
        if os.path.exists(self.config_path):
            self.config.read(self.config_path, encoding="utf-8")
            logger.info(f"Konfiguration geladen: {self.config_path}")
        else:
            logger.info("Keine config.ini gefunden, verwende Standardwerte")
            self.save()  # Standarddatei erstellen

    def save(self):
        """Speichert die aktuelle Konfiguration."""
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("; ============================================\n")
            f.write("; ZVT-zu-SumUp Gateway - Konfiguration\n")
            f.write("; ============================================\n")
            f.write("; Diese Datei kann mit einem Texteditor\n")
            f.write("; bearbeitet werden. Alternativ: setup.bat\n")
            f.write("; ============================================\n\n")
            self.config.write(f)
        logger.info(f"Konfiguration gespeichert: {self.config_path}")

    # ── Getter ────────────────────────────────────────────────────

    @property
    def modus(self) -> str:
        return self.config.get("gateway", "modus")

    @property
    def tcp_port(self) -> int:
        return self.config.getint("gateway", "tcp_port")

    @property
    def tcp_host(self) -> str:
        return self.config.get("gateway", "tcp_host")

    @property
    def com_port(self) -> str:
        return self.config.get("gateway", "com_port")

    @property
    def com_baudrate(self) -> int:
        return self.config.getint("gateway", "com_baudrate")

    @property
    def waehrung(self) -> str:
        return self.config.get("gateway", "waehrung")

    @property
    def log_level(self) -> str:
        return self.config.get("gateway", "log_level")

    @property
    def log_datei(self) -> str:
        return self.config.get("gateway", "log_datei")

    @property
    def api_key(self) -> str:
        return self.config.get("sumup", "api_key")

    @property
    def merchant_code(self) -> str:
        return self.config.get("sumup", "merchant_code")

    @property
    def terminal_id(self) -> str:
        return self.config.get("sumup", "terminal_id")

    @property
    def affiliate_key(self) -> str:
        return self.config.get("sumup", "affiliate_key")

    @property
    def affiliate_app_id(self) -> str:
        return self.config.get("sumup", "affiliate_app_id")

    @property
    def zahlung_timeout(self) -> int:
        return self.config.getint("sumup", "zahlung_timeout")

    # ── Setter ────────────────────────────────────────────────────

    def set(self, section: str, key: str, value: str):
        """Setzt einen Konfigurationswert."""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))

    # ── Validierung ───────────────────────────────────────────────

    def validate(self) -> list:
        """
        Prueft die Konfiguration auf Fehler.
        Gibt eine Liste von Fehlermeldungen zurueck (leer = OK).
        """
        errors = []

        if not self.api_key:
            errors.append("SumUp API-Schluessel fehlt (sumup > api_key)")

        if self.modus not in ("tcp", "com"):
            errors.append(f"Ungueltiger Modus: '{self.modus}' (erlaubt: tcp, com)")

        if self.modus == "tcp":
            if not (1 <= self.tcp_port <= 65535):
                errors.append(f"Ungueltiger TCP-Port: {self.tcp_port}")

        if self.modus == "com":
            if not self.com_port:
                errors.append("COM-Port nicht angegeben")

        return errors
