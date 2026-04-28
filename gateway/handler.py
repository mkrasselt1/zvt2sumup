"""
ZVT-Kommando-Handler.

Verarbeitet eingehende ZVT-Kommandos vom Kassensystem und
uebersetzt sie in SumUp-API-Aufrufe.
"""

import time
import logging
from typing import List

from . import zvt_protocol as zvt
from .sumup_api import SumUpClient, SumUpError

logger = logging.getLogger("zvt2sumup.handler")


class ZVTGatewayHandler:
    """
    Zentrale Logik: Empfaengt ZVT-Kommandos, fuehrt SumUp-Aktionen aus,
    gibt ZVT-Antworten zurueck.
    """

    def __init__(self, sumup: SumUpClient, currency: str = "EUR",
                 payment_timeout: int = 120):
        self.sumup = sumup
        self.currency = currency
        self.payment_timeout = payment_timeout
        self.registered = False
        self.last_checkout_id = None
        self.last_transaction_id = None

    def handle(self, command: zvt.ZVTCommand) -> List[bytes]:
        """
        Haupteingang: Verarbeitet ein ZVT-Kommando.

        Args:
            command: Das empfangene ZVT-Kommando

        Returns:
            Liste von ZVT-Antwort-APDUs
        """
        logger.info(f">> Verarbeite: {command.name}")

        cmd_id = command.command_id
        handlers = {
            zvt.ZVTCommand.REGISTRATION: self._handle_registration,
            zvt.ZVTCommand.AUTHORIZATION: self._handle_authorization,
            zvt.ZVTCommand.REVERSAL: self._handle_reversal,
            zvt.ZVTCommand.END_OF_DAY: self._handle_end_of_day,
            zvt.ZVTCommand.STATUS_ENQUIRY: self._handle_status_enquiry,
            zvt.ZVTCommand.ABORT: self._handle_abort,
            zvt.ZVTCommand.LOG_OFF: self._handle_log_off,
            zvt.ZVTCommand.DIAGNOSIS: self._handle_diagnosis,
        }

        handler_func = handlers.get(cmd_id)
        if handler_func:
            try:
                return handler_func(command)
            except Exception as e:
                logger.error(f"Fehler bei {command.name}: {e}", exc_info=True)
                return [zvt.ZVTResponse.abort(result_code=0x6F)]
        else:
            logger.warning(f"Nicht unterstuetztes Kommando: {command}")
            return [zvt.ZVTResponse.abort(result_code=0xB2)]

    # ── Registrierung (06 00) ─────────────────────────────────────

    def _handle_registration(self, command: zvt.ZVTCommand) -> List[bytes]:
        """
        Registrierung des Kassensystems.

        Das Kassensystem meldet sich am Terminal an. Wir pruefen
        die SumUp-Verbindung und bestaetigen.
        """
        logger.info("Registrierung: Pruefe SumUp-Verbindung...")

        responses = []

        # Zwischenstatus senden
        responses.append(zvt.ZVTResponse.intermediate_status("Pruefe SumUp-Verbindung..."))

        conn = self.sumup.test_connection()
        if conn["ok"] and conn.get("merchant_code_ok", True):
            self.registered = True
            logger.info("Registrierung erfolgreich")

            # Completion mit Terminal-ID
            terminal_info = self._build_registration_response()
            responses.append(zvt.ZVTResponse.completion(terminal_info))
        else:
            logger.error("Registrierung fehlgeschlagen: SumUp nicht erreichbar")
            responses.append(zvt.ZVTResponse.abort(result_code=0x83))

        return responses

    def _build_registration_response(self) -> bytes:
        """Baut die Registrierungs-Antwortdaten."""
        data = bytearray()
        # Tag 27: Ergebniscode 0 = OK
        data.extend([0x27, 0x00])
        # Tag 29: Terminal-ID (8 Bytes, ASCII)
        tid = (self.sumup.terminal_id or "SUMUP001")[:8].ljust(8)
        data.extend([0x29, len(tid.encode())])
        data.extend(tid.encode("ascii"))
        return bytes(data)

    # ── Autorisierung / Zahlung (06 01) ───────────────────────────

    def _handle_authorization(self, command: zvt.ZVTCommand) -> List[bytes]:
        """
        Autorisierung (Kartenzahlung).

        Ablauf:
        1. Betrag aus ZVT-Daten extrahieren
        2. SumUp-Checkout erstellen
        3. An Terminal senden
        4. Auf Ergebnis warten (Polling)
        5. ZVT-Antwort zurueckgeben
        """
        responses = []

        # Betrag extrahieren
        amount_cents = zvt.extract_amount(command.data)
        if amount_cents is None or amount_cents <= 0:
            logger.error("Kein gueltiger Betrag im Kommando")
            return [zvt.ZVTResponse.abort(result_code=0x6F)]

        amount_eur = amount_cents / 100.0
        logger.info(f"Zahlung: {amount_eur:.2f} {self.currency}")

        # Zwischenstatus: Zahlung wird vorbereitet
        responses.append(
            zvt.ZVTResponse.intermediate_status(f"Zahlung {amount_eur:.2f} EUR...")
        )

        try:
            # 1. Checkout erstellen
            checkout = self.sumup.create_checkout(
                amount_cents=amount_cents,
                currency=self.currency,
                description=f"Kassenzahlung {amount_eur:.2f} {self.currency}",
            )
            checkout_id = checkout.get("id")
            if not checkout_id:
                raise SumUpError("Keine Checkout-ID erhalten", "NO_ID")

            self.last_checkout_id = checkout_id

            # 2. An Terminal senden
            responses.append(
                zvt.ZVTResponse.intermediate_status("Bitte Karte am Terminal...")
            )

            if self.sumup.terminal_id:
                self.sumup.process_checkout_on_terminal(checkout_id)

            # 3. Auf Ergebnis warten
            def on_status(status, data):
                pass  # Status-Updates koennten hier verarbeitet werden

            result = self.sumup.wait_for_payment(
                checkout_id,
                timeout=self.payment_timeout,
                on_status_update=on_status,
            )

            status = result.get("status", "UNKNOWN")

            if status == "PAID":
                self.last_transaction_id = result.get("transaction_id")

                # Erfolg: Completion mit Zahlungsdaten
                completion_data = self._build_payment_completion(result, amount_cents)
                responses.append(zvt.ZVTResponse.completion(completion_data))
                logger.info(f"Zahlung erfolgreich: {amount_eur:.2f} {self.currency}")

            elif status == "TIMEOUT":
                logger.warning("Zahlung: Timeout")
                responses.append(zvt.ZVTResponse.abort(result_code=0x68))

            else:
                logger.warning(f"Zahlung fehlgeschlagen: {status}")
                responses.append(zvt.ZVTResponse.abort(result_code=0x6F))

        except SumUpError as e:
            logger.error(f"SumUp-Fehler: {e}")
            responses.append(
                zvt.ZVTResponse.intermediate_status(f"Fehler: {str(e)[:30]}")
            )
            responses.append(zvt.ZVTResponse.abort(result_code=0x83))

        return responses

    def _build_payment_completion(self, result: dict, amount_cents: int) -> bytes:
        """Baut die Zahlungs-Completion-Daten."""
        data = bytearray()

        # Tag 27: Ergebniscode 0 = OK
        data.extend([0x27, 0x00])

        # Tag 04: Betrag (6 Bytes BCD)
        data.append(0x04)
        data.extend(zvt.int_to_bcd(amount_cents, 6))

        # Tag 0B: Trace-Nummer (3 Bytes BCD)
        trace = int(time.time()) % 999999
        data.append(0x0B)
        data.extend(zvt.int_to_bcd(trace, 3))

        # Tag 22: Kartentyp (2 Bytes) - generisch
        data.extend([0x22, 0x00, 0x00])

        return bytes(data)

    # ── Storno (06 30) ────────────────────────────────────────────

    def _handle_reversal(self, command: zvt.ZVTCommand) -> List[bytes]:
        """
        Storno / Rueckerstattung der letzten Transaktion.
        """
        responses = []
        responses.append(
            zvt.ZVTResponse.intermediate_status("Storno wird ausgefuehrt...")
        )

        if not self.last_transaction_id:
            logger.warning("Storno: Keine vorherige Transaktion bekannt")
            return [zvt.ZVTResponse.abort(result_code=0x64)]

        try:
            result = self.sumup.refund_transaction(self.last_transaction_id)
            logger.info(f"Storno erfolgreich fuer TX {self.last_transaction_id}")

            # Completion
            data = bytearray([0x27, 0x00])  # Ergebniscode OK
            responses.append(zvt.ZVTResponse.completion(bytes(data)))
            self.last_transaction_id = None

        except SumUpError as e:
            logger.error(f"Storno fehlgeschlagen: {e}")
            responses.append(zvt.ZVTResponse.abort(result_code=0x6F))

        return responses

    # ── Kassenschnitt / Tagesabschluss (06 50) ────────────────────

    def _handle_end_of_day(self, command: zvt.ZVTCommand) -> List[bytes]:
        """
        Kassenschnitt / Tagesabschluss.

        Da SumUp automatisch abrechnet, liefern wir hier eine
        Zusammenfassung der letzten Transaktionen.
        """
        responses = []
        responses.append(
            zvt.ZVTResponse.intermediate_status("Kassenschnitt...")
        )

        try:
            transactions = self.sumup.get_transaction_history(limit=50)

            total_amount = 0
            count = 0
            for tx in transactions:
                if tx.get("status") == "SUCCESSFUL":
                    total_amount += int(tx.get("amount", 0) * 100)
                    count += 1

            logger.info(f"Kassenschnitt: {count} Transaktionen, Summe: {total_amount / 100:.2f} EUR")

            # Status-Info mit Zusammenfassung
            summary_data = bytearray()
            summary_data.extend([0x27, 0x00])  # Ergebniscode OK

            responses.append(zvt.ZVTResponse.completion(bytes(summary_data)))

            # Druckzeilen
            responses.append(zvt.ZVTResponse.print_line(f"Transaktionen: {count}"))
            responses.append(zvt.ZVTResponse.print_line(f"Gesamtsumme: {total_amount / 100:.2f} EUR"))
            responses.append(zvt.ZVTResponse.print_line("(SumUp rechnet automatisch ab)"))

        except Exception as e:
            logger.error(f"Kassenschnitt-Fehler: {e}")
            # Trotzdem Completion senden (Kassenschnitt ist bei SumUp nicht kritisch)
            responses.append(zvt.ZVTResponse.completion(bytes([0x27, 0x00])))

        return responses

    # ── Statusabfrage (05 01) ─────────────────────────────────────

    def _handle_status_enquiry(self, command: zvt.ZVTCommand) -> List[bytes]:
        """Statusabfrage: Gibt den aktuellen Terminal-Status zurueck."""
        connected = self.sumup.test_connection()["ok"]

        data = bytearray()
        data.extend([0x27, 0x00 if connected else 0x83])

        return [zvt.ZVTResponse.status_info(bytes(data))]

    # ── Abbruch (06 B0) ──────────────────────────────────────────

    def _handle_abort(self, command: zvt.ZVTCommand) -> List[bytes]:
        """Abbruch: Bestaetigt den Abbruch."""
        logger.info("Abbruch empfangen")
        return [zvt.ZVTResponse.completion(bytes([0x27, 0x00]))]

    # ── Abmeldung (06 02) ────────────────────────────────────────

    def _handle_log_off(self, command: zvt.ZVTCommand) -> List[bytes]:
        """Abmeldung des Kassensystems."""
        self.registered = False
        logger.info("Kassensystem abgemeldet")
        return [zvt.ZVTResponse.completion()]

    # ── Diagnose (06 70) ──────────────────────────────────────────

    def _handle_diagnosis(self, command: zvt.ZVTCommand) -> List[bytes]:
        """Diagnose: Prueft die Verbindung."""
        responses = []
        responses.append(
            zvt.ZVTResponse.intermediate_status("Diagnose laeuft...")
        )

        connected = self.sumup.test_connection()["ok"]
        if connected:
            responses.append(zvt.ZVTResponse.completion(bytes([0x27, 0x00])))
        else:
            responses.append(zvt.ZVTResponse.abort(result_code=0x83))

        return responses
