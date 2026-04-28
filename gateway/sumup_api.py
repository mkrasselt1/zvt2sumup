"""
SumUp API Client.

Kommuniziert mit der SumUp Cloud-API um Zahlungen auf dem
SumUp Solo Terminal auszuloesen und deren Status abzufragen.

API-Dokumentation: https://developer.sumup.com/api
"""

import time
import logging
import requests
from typing import Optional

logger = logging.getLogger("zvt2sumup.sumup")

# SumUp API Basis-URL
API_BASE = "https://api.sumup.com"

# Timeout fuer API-Aufrufe (Sekunden)
API_TIMEOUT = 15

# Maximale Wartezeit auf Zahlungsabschluss (Sekunden)
PAYMENT_TIMEOUT = 120

# Poll-Intervall beim Warten auf Zahlung (Sekunden)
POLL_INTERVAL = 2


class SumUpError(Exception):
    """Fehler bei der SumUp-API-Kommunikation."""

    def __init__(self, message: str, code: str = "UNKNOWN"):
        super().__init__(message)
        self.code = code


class SumUpClient:
    """Client fuer die SumUp Merchant API."""

    def __init__(self, api_key: str, merchant_code: str = "", terminal_id: Optional[str] = None):
        """
        Initialisiert den SumUp-Client.

        Args:
            api_key: SumUp API-Schluessel (Bearer Token)
            merchant_code: SumUp Haendler-Code (wird automatisch ermittelt wenn leer)
            terminal_id: Optionale Terminal-ID des SumUp Solo
        """
        self.api_key = api_key
        self.merchant_code = merchant_code
        self.terminal_id = terminal_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def test_connection(self) -> dict:
        """
        Testet die Verbindung zur SumUp-API und ermittelt den Merchant Code.

        Der Merchant Code wird automatisch aus dem SumUp-Konto gelesen
        und auf dem Client gesetzt - muss nicht manuell eingegeben werden.

        Returns:
            Dict mit Ergebnis:
            - ok: True/False
            - error: Fehlermeldung (nur bei ok=False)
            - business_name: Geschaeftsname (nur bei ok=True)
            - merchant_code: Merchant Code vom SumUp-Konto (nur bei ok=True)
        """
        result = {"ok": False}
        try:
            resp = self.session.get(
                f"{API_BASE}/v0.1/me",
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                profile = data.get("merchant_profile", {})
                actual_code = profile.get("merchant_code", data.get("merchant_code", ""))
                business_name = profile.get("business_name", "")

                result["ok"] = True
                result["business_name"] = business_name
                result["merchant_code"] = actual_code

                # Merchant Code automatisch uebernehmen
                if actual_code:
                    self.merchant_code = actual_code
                    logger.info(f"SumUp-Verbindung OK. Haendler: {business_name or actual_code} ({actual_code})")
                else:
                    logger.info(f"SumUp-Verbindung OK. Haendler: {business_name or 'Unbekannt'}")

            elif resp.status_code == 401:
                result["error"] = "API-Schluessel ungueltig oder abgelaufen"
                logger.error("SumUp-API: Authentifizierung fehlgeschlagen (401)")
            elif resp.status_code == 403:
                result["error"] = "API-Schluessel hat nicht genuegend Berechtigungen"
                logger.error("SumUp-API: Zugriff verweigert (403)")
            else:
                result["error"] = f"SumUp-API-Fehler: {resp.status_code}"
                logger.error(f"SumUp-API-Fehler: {resp.status_code} {resp.text}")

        except requests.ConnectionError:
            result["error"] = "Keine Internetverbindung oder SumUp nicht erreichbar"
            logger.error("SumUp-Verbindungsfehler: Keine Verbindung")
        except requests.Timeout:
            result["error"] = "SumUp-API antwortet nicht (Timeout)"
            logger.error("SumUp-Verbindungsfehler: Timeout")
        except requests.RequestException as e:
            result["error"] = f"Netzwerkfehler: {e}"
            logger.error(f"SumUp-Verbindungsfehler: {e}")

        return result

    def get_terminals(self) -> list:
        """Listet alle verfuegbaren Terminals auf."""
        try:
            resp = self.session.get(
                f"{API_BASE}/v0.1/merchants/{self.merchant_code}/terminals",
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                terminals = resp.json().get("items", [])
                logger.info(f"{len(terminals)} Terminal(s) gefunden")
                return terminals
            else:
                logger.warning(f"Terminals konnten nicht abgefragt werden: {resp.status_code}")
                return []
        except requests.RequestException as e:
            logger.error(f"Fehler beim Abrufen der Terminals: {e}")
            return []

    def create_checkout(self, amount_cents: int, currency: str = "EUR",
                        description: str = "", reference: str = "") -> dict:
        """
        Erstellt einen neuen Checkout (Zahlungsvorgang).

        Args:
            amount_cents: Betrag in Cent
            currency: Waehrung (Standard: EUR)
            description: Beschreibung der Zahlung
            reference: Externe Referenz (z.B. Rechnungsnummer)

        Returns:
            Checkout-Daten als Dictionary
        """
        amount = amount_cents / 100.0

        payload = {
            "checkout_reference": reference or f"ZVT-{int(time.time())}",
            "amount": amount,
            "currency": currency,
            "merchant_code": self.merchant_code,
            "description": description or "ZVT-Zahlung",
        }

        logger.info(f"Erstelle Checkout: {amount:.2f} {currency} (Ref: {payload['checkout_reference']})")

        try:
            resp = self.session.post(
                f"{API_BASE}/v0.1/checkouts",
                json=payload,
                timeout=API_TIMEOUT,
            )

            if resp.status_code in (200, 201):
                checkout = resp.json()
                logger.info(f"Checkout erstellt: ID={checkout.get('id')}")
                return checkout
            else:
                error_msg = resp.json().get("message", resp.text)
                logger.error(f"Checkout-Fehler: {resp.status_code} - {error_msg}")
                raise SumUpError(f"Checkout fehlgeschlagen: {error_msg}", "CHECKOUT_FAILED")

        except requests.RequestException as e:
            logger.error(f"Netzwerkfehler beim Checkout: {e}")
            raise SumUpError(f"Netzwerkfehler: {e}", "NETWORK_ERROR")

    def process_checkout_on_terminal(self, checkout_id: str) -> dict:
        """
        Sendet einen Checkout an das SumUp Solo Terminal zur Verarbeitung.

        Args:
            checkout_id: Die Checkout-ID von create_checkout()

        Returns:
            Aktualisierte Checkout-Daten
        """
        if not self.terminal_id:
            raise SumUpError("Keine Terminal-ID konfiguriert", "NO_TERMINAL")

        logger.info(f"Sende Checkout {checkout_id} an Terminal {self.terminal_id}")

        try:
            resp = self.session.put(
                f"{API_BASE}/v0.1/checkouts/{checkout_id}",
                json={"terminal_id": self.terminal_id},
                timeout=API_TIMEOUT,
            )

            if resp.status_code in (200, 201, 204):
                result = resp.json() if resp.text else {}
                logger.info(f"Checkout an Terminal gesendet")
                return result
            else:
                error_msg = resp.json().get("message", resp.text) if resp.text else str(resp.status_code)
                logger.error(f"Terminal-Fehler: {resp.status_code} - {error_msg}")
                raise SumUpError(f"Terminal-Verarbeitung fehlgeschlagen: {error_msg}", "TERMINAL_FAILED")

        except requests.RequestException as e:
            logger.error(f"Netzwerkfehler: {e}")
            raise SumUpError(f"Netzwerkfehler: {e}", "NETWORK_ERROR")

    def get_checkout_status(self, checkout_id: str) -> dict:
        """
        Fragt den aktuellen Status eines Checkouts ab.

        Returns:
            Checkout-Daten mit Status-Feld:
            - PENDING: Wartet auf Verarbeitung
            - PAID: Erfolgreich bezahlt
            - FAILED: Fehlgeschlagen
            - EXPIRED: Abgelaufen
        """
        try:
            resp = self.session.get(
                f"{API_BASE}/v0.1/checkouts/{checkout_id}",
                timeout=API_TIMEOUT,
            )

            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Status-Abfrage fehlgeschlagen: {resp.status_code}")
                return {"status": "UNKNOWN"}

        except requests.RequestException as e:
            logger.error(f"Status-Abfrage Netzwerkfehler: {e}")
            return {"status": "UNKNOWN"}

    def wait_for_payment(self, checkout_id: str,
                         timeout: int = PAYMENT_TIMEOUT,
                         on_status_update=None) -> dict:
        """
        Wartet auf den Abschluss einer Zahlung (Polling).

        Args:
            checkout_id: Checkout-ID
            timeout: Maximale Wartezeit in Sekunden
            on_status_update: Callback fuer Statusaenderungen (optional)

        Returns:
            Finales Checkout-Ergebnis
        """
        start = time.time()
        last_status = None

        logger.info(f"Warte auf Zahlung {checkout_id} (max. {timeout}s)...")

        while time.time() - start < timeout:
            result = self.get_checkout_status(checkout_id)
            status = result.get("status", "UNKNOWN")

            if status != last_status:
                logger.info(f"Zahlungsstatus: {status}")
                last_status = status
                if on_status_update:
                    on_status_update(status, result)

            if status == "PAID":
                logger.info(f"Zahlung erfolgreich! TX-ID: {result.get('transaction_id', 'N/A')}")
                return result

            if status in ("FAILED", "EXPIRED"):
                logger.warning(f"Zahlung fehlgeschlagen: {status}")
                return result

            time.sleep(POLL_INTERVAL)

        logger.warning("Zahlung: Timeout erreicht")
        return {"status": "TIMEOUT", "checkout_id": checkout_id}

    def refund_transaction(self, transaction_id: str, amount_cents: Optional[int] = None) -> dict:
        """
        Fuehrt eine Rueckerstattung (Storno) durch.

        Args:
            transaction_id: Die Transaction-ID der urspruenglichen Zahlung
            amount_cents: Optionaler Teilbetrag in Cent (None = volle Rueckerstattung)

        Returns:
            Rueckerstattungs-Daten
        """
        logger.info(f"Storno fuer Transaktion {transaction_id}")

        payload = {}
        if amount_cents is not None:
            payload["amount"] = amount_cents / 100.0

        try:
            resp = self.session.post(
                f"{API_BASE}/v0.1/me/refund/{transaction_id}",
                json=payload if payload else None,
                timeout=API_TIMEOUT,
            )

            if resp.status_code in (200, 201, 204):
                result = resp.json() if resp.text else {"status": "OK"}
                logger.info(f"Storno erfolgreich")
                return result
            else:
                error_msg = resp.json().get("message", resp.text) if resp.text else str(resp.status_code)
                logger.error(f"Storno-Fehler: {resp.status_code} - {error_msg}")
                raise SumUpError(f"Storno fehlgeschlagen: {error_msg}", "REFUND_FAILED")

        except requests.RequestException as e:
            logger.error(f"Netzwerkfehler beim Storno: {e}")
            raise SumUpError(f"Netzwerkfehler: {e}", "NETWORK_ERROR")

    def get_transaction_history(self, limit: int = 10) -> list:
        """Ruft die letzten Transaktionen ab (fuer Kassenschnitt)."""
        try:
            resp = self.session.get(
                f"{API_BASE}/v0.1/me/transactions/history",
                params={"limit": limit, "order": "descending"},
                timeout=API_TIMEOUT,
            )

            if resp.status_code == 200:
                items = resp.json().get("items", [])
                return items
            else:
                logger.warning(f"Transaktionsverlauf-Fehler: {resp.status_code}")
                return []

        except requests.RequestException as e:
            logger.error(f"Netzwerkfehler: {e}")
            return []
