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

    def __init__(self, api_key: str, merchant_code: str = "", terminal_id: Optional[str] = None,
                 affiliate_key: str = "", affiliate_app_id: str = ""):
        """
        Initialisiert den SumUp-Client.

        Args:
            api_key: SumUp API-Schluessel (Bearer Token)
            merchant_code: SumUp Haendler-Code (wird automatisch ermittelt wenn leer)
            terminal_id: Optionale Terminal-ID des SumUp Solo
            affiliate_key: SumUp Affiliate-Key (fuer Cloud API Checkouts)
            affiliate_app_id: App-ID zum Affiliate-Key
        """
        self.api_key = api_key
        self.merchant_code = merchant_code
        self.terminal_id = terminal_id
        self.affiliate_key = affiliate_key
        self.affiliate_app_id = affiliate_app_id
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
        """Listet alle verfuegbaren Terminals und Readers auf."""
        terminals = []

        # Klassische Terminals API
        try:
            resp = self.session.get(
                f"{API_BASE}/v0.1/merchants/{self.merchant_code}/terminals",
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                terminals.extend(resp.json().get("items", []))
            else:
                logger.warning(f"Terminals konnten nicht abgefragt werden: {resp.status_code}")
        except requests.RequestException as e:
            logger.error(f"Fehler beim Abrufen der Terminals: {e}")

        # Neuere Readers API (SumUp Solo, Solo Lite, etc.)
        try:
            resp = self.session.get(
                f"{API_BASE}/v0.1/merchants/{self.merchant_code}/readers",
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                readers = resp.json().get("items", [])
                for r in readers:
                    # Reader-Daten auf Terminal-Format normalisieren
                    if not r.get("id") and r.get("identifier"):
                        r["id"] = r["identifier"]
                    terminals.append(r)
            else:
                logger.debug(f"Readers konnten nicht abgefragt werden: {resp.status_code}")
        except requests.RequestException as e:
            logger.debug(f"Fehler beim Abrufen der Readers: {e}")

        logger.info(f"{len(terminals)} Terminal(s)/Reader(s) gefunden")
        return terminals

    def pair_reader(self, pairing_code: str, name: str = "ZVT-Gateway Terminal") -> dict:
        """
        Koppelt einen SumUp Reader (Solo, Solo Lite) ueber den Pairing-Code.

        Der Code wird auf dem Geraet angezeigt unter:
        Einstellungen > Verbindungen > API > Verbinden

        Args:
            pairing_code: 8-9-stelliger alphanumerischer Code vom Geraet
            name: Anzeigename fuer den Reader

        Returns:
            Reader-Daten als Dictionary (mit id, name, status, device)
        """
        # Leerzeichen, Bindestriche und Punkte entfernen
        clean_code = pairing_code.strip().replace("-", "").replace(" ", "").replace(".", "").upper()

        payload = {
            "pairing_code": clean_code,
            "name": name,
        }

        logger.info(f"Kopple Reader mit Code {pairing_code[:3]}...")

        try:
            resp = self.session.post(
                f"{API_BASE}/v0.1/merchants/{self.merchant_code}/readers",
                json=payload,
                timeout=API_TIMEOUT,
            )

            if resp.status_code in (200, 201):
                reader = resp.json()
                logger.info(f"Reader gekoppelt: ID={reader.get('id')}, Status={reader.get('status')}")
                return reader
            else:
                error_msg = resp.json().get("message", resp.text) if resp.text else str(resp.status_code)
                logger.error(f"Reader-Kopplung fehlgeschlagen: {resp.status_code} - {error_msg}")
                raise SumUpError(f"Kopplung fehlgeschlagen: {error_msg}", "PAIRING_FAILED")

        except requests.RequestException as e:
            logger.error(f"Netzwerkfehler bei Reader-Kopplung: {e}")
            raise SumUpError(f"Netzwerkfehler: {e}", "NETWORK_ERROR")

    @property
    def is_reader(self) -> bool:
        """Prueft ob die Terminal-ID ein Reader ist (Solo, Solo Lite)."""
        return bool(self.terminal_id and self.terminal_id.startswith("rdr_"))

    def create_checkout(self, amount_cents: int, currency: str = "EUR",
                        description: str = "", reference: str = "") -> dict:
        """
        Erstellt einen neuen Checkout (Zahlungsvorgang).
        Erkennt automatisch ob Reader-API oder klassische API verwendet wird.

        Returns:
            Checkout-Daten als Dictionary (mit 'id' oder 'client_transaction_id')
        """
        if self.is_reader:
            return self._create_reader_checkout(amount_cents, currency, description)
        else:
            return self._create_classic_checkout(amount_cents, currency, description, reference)

    def _create_classic_checkout(self, amount_cents: int, currency: str,
                                  description: str, reference: str) -> dict:
        """Klassischer Checkout (alte Terminal-API)."""
        amount = amount_cents / 100.0

        payload = {
            "checkout_reference": reference or f"ZVT-{int(time.time())}",
            "amount": amount,
            "currency": currency,
            "merchant_code": self.merchant_code,
            "description": description or "ZVT-Zahlung",
        }

        if self.affiliate_key and self.affiliate_app_id:
            payload["affiliate"] = {
                "key": self.affiliate_key,
                "app_id": self.affiliate_app_id,
            }

        logger.info(f"Erstelle Checkout: {amount:.2f} {currency}")

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

    def _create_reader_checkout(self, amount_cents: int, currency: str,
                                 description: str) -> dict:
        """Reader-Checkout (Solo, Solo Lite) - sendet direkt an den Reader."""
        if not self.terminal_id:
            raise SumUpError("Keine Reader-ID konfiguriert", "NO_TERMINAL")

        payload = {
            "total_amount": {
                "currency": currency,
                "minor_unit": 2,
                "value": amount_cents,
            },
        }

        if description:
            payload["description"] = description

        if self.affiliate_key and self.affiliate_app_id:
            payload["affiliate"] = {
                "key": self.affiliate_key,
                "app_id": self.affiliate_app_id,
            }

        logger.info(f"Erstelle Reader-Checkout: {amount_cents / 100:.2f} {currency} -> {self.terminal_id}")

        try:
            resp = self.session.post(
                f"{API_BASE}/v0.1/merchants/{self.merchant_code}/readers/{self.terminal_id}/checkout",
                json=payload,
                timeout=API_TIMEOUT,
            )

            if resp.status_code in (200, 201):
                result = resp.json()
                # Reader-API gibt {data: {client_transaction_id: ...}} zurueck
                data = result.get("data", result)
                tx_id = data.get("client_transaction_id", "")
                logger.info(f"Reader-Checkout erstellt: TX-ID={tx_id}")
                # Normalisieren: 'id' setzen fuer einheitliche Weiterverarbeitung
                return {"id": tx_id, "client_transaction_id": tx_id, "status": "PENDING", "_reader": True}
            else:
                error_msg = ""
                try:
                    err_json = resp.json()
                    error_msg = err_json.get("detail", err_json.get("message", resp.text))
                except Exception:
                    error_msg = resp.text
                logger.error(f"Reader-Checkout-Fehler: {resp.status_code} - {error_msg}")
                raise SumUpError(f"Reader-Checkout fehlgeschlagen: {error_msg}", "CHECKOUT_FAILED")

        except requests.RequestException as e:
            logger.error(f"Netzwerkfehler beim Reader-Checkout: {e}")
            raise SumUpError(f"Netzwerkfehler: {e}", "NETWORK_ERROR")

    def process_checkout_on_terminal(self, checkout_id: str) -> dict:
        """
        Sendet einen Checkout an das Terminal zur Verarbeitung.
        Bei Readern (Solo) ist dies nicht noetig - der Checkout geht direkt ans Geraet.
        """
        # Reader-Checkouts gehen direkt ans Geraet, kein separater Schritt noetig
        if self.is_reader:
            logger.info("Reader-Checkout: Zahlung bereits am Geraet")
            return {}

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
        Unterstuetzt sowohl klassische Checkouts als auch Reader-Transaktionen.
        """
        # Fuer Reader: Transaktionsstatus ueber Transactions-API abfragen
        if self.is_reader:
            return self._get_reader_transaction_status(checkout_id)

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

    def _get_reader_status(self) -> dict:
        """Fragt den aktuellen Geraete-Status des Readers ab."""
        try:
            resp = self.session.get(
                f"{API_BASE}/v0.1/merchants/{self.merchant_code}/readers/{self.terminal_id}/status",
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", resp.json())
                return data
        except requests.RequestException:
            pass
        return {}

    def _find_transaction(self, client_transaction_id: str) -> Optional[dict]:
        """Sucht eine Transaktion in der SumUp-Historie."""
        try:
            # Letzte Transaktionen abrufen und nach client_transaction_id suchen
            resp = self.session.get(
                f"{API_BASE}/v0.1/me/transactions/history",
                params={"limit": 5, "order": "descending"},
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                for tx in items:
                    if tx.get("client_transaction_id") == client_transaction_id:
                        return tx
        except requests.RequestException:
            pass

        return None

    def _map_transaction_to_checkout_status(self, tx: dict) -> dict:
        """Mappt SumUp-Transaktionsstatus auf Checkout-Status."""
        tx_status = tx.get("status", "").upper()
        status_map = {
            "SUCCESSFUL": "PAID",
            "CANCELLED": "FAILED",
            "FAILED": "FAILED",
            "PENDING": "PENDING",
        }
        # Unbekannte Status als FAILED behandeln, nicht als PENDING
        mapped = status_map.get(tx_status, "FAILED")
        return {
            "status": mapped,
            "transaction_id": tx.get("transaction_id", tx.get("id", "")),
            "transaction_code": tx.get("transaction_code", ""),
            "client_transaction_id": tx.get("client_transaction_id", ""),
            "amount": tx.get("amount", 0),
            "currency": tx.get("currency", ""),
            "card_type": tx.get("card_type", ""),
        }

    def wait_for_payment(self, checkout_id: str,
                         timeout: int = PAYMENT_TIMEOUT,
                         on_status_update=None) -> dict:
        """
        Wartet auf den Abschluss einer Zahlung (Polling).
        Funktioniert fuer klassische Checkouts und Reader-Checkouts.
        """
        if self.is_reader:
            return self._wait_for_reader_payment(checkout_id, timeout, on_status_update)
        return self._wait_for_classic_payment(checkout_id, timeout, on_status_update)

    def _wait_for_classic_payment(self, checkout_id: str, timeout: int,
                                   on_status_update=None) -> dict:
        """Polling fuer klassische Checkouts."""
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

    def _wait_for_reader_payment(self, client_transaction_id: str, timeout: int,
                                  on_status_update=None) -> dict:
        """
        Polling fuer Reader-Checkouts (Solo, Solo Lite).

        Ablauf:
        1. Transaktion in der Historie suchen (erscheint dort sobald abgeschlossen)
        2. Nebenbei Reader-State loggen damit der Benutzer sieht was passiert
        3. Gesamtes Timeout abwarten bevor aufgegeben wird
        """
        start = time.time()
        last_state = None

        logger.info(f"Warte auf Reader-Zahlung {client_transaction_id} (max. {timeout}s)...")

        while time.time() - start < timeout:
            # Transaktion in der Historie suchen
            tx = self._find_transaction(client_transaction_id)
            if tx:
                result = self._map_transaction_to_checkout_status(tx)
                status = result["status"]

                # Nur bei Endzustand zurueckgeben, bei PENDING weiter warten
                if status in ("PAID", "FAILED", "EXPIRED"):
                    logger.info(f"Transaktion abgeschlossen: {status} "
                               f"(nach {time.time() - start:.1f}s)")
                    if on_status_update:
                        on_status_update(status, result)
                    return result

                if status != last_state:
                    logger.info(f"Transaktionsstatus: {status}")
                    last_state = status
            else:
                # Reader-State abfragen und loggen
                reader_status = self._get_reader_status()
                reader_state = reader_status.get("state", "UNKNOWN")

                if reader_state != last_state:
                    logger.info(f"Reader-State: {reader_state}")
                    last_state = reader_state
                    if on_status_update:
                        on_status_update("PENDING", {"reader_state": reader_state})

            time.sleep(POLL_INTERVAL)

        logger.warning("Zahlung: Timeout erreicht")
        return {"status": "TIMEOUT", "checkout_id": client_transaction_id}

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
