"""
ZVT/SumUp Test-Tool

Zwei Modi:
  1) Kassen-Simulator: Verbindet sich als ZVT-Kasse mit dem Gateway,
     sendet Befehle (Registrierung, Zahlung, Storno, Kassenschnitt)
     und zeigt alle Antworten des Gateways an.

  2) Terminal-Tester: Sendet Zahlungsanforderungen direkt an das
     SumUp-Terminal ueber die Cloud-API (ohne ZVT/Gateway).

Aufruf: python test_tool.py
"""

import socket
import struct
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gateway.config import GatewayConfig
from gateway.sumup_api import SumUpClient, SumUpError


# ── ZVT Hilfsfunktionen ──────────────────────────────────────────

def build_tcp_message(apdu: bytes) -> bytes:
    """Verpackt eine APDU als TCP-ZVT-Nachricht (2-Byte Laenge + APDU)."""
    return struct.pack(">H", len(apdu)) + apdu


def int_to_bcd(value: int, num_bytes: int) -> bytes:
    """Wandelt eine Ganzzahl in BCD-Bytes um."""
    s = str(value).zfill(num_bytes * 2)
    result = []
    for i in range(0, len(s), 2):
        result.append(int(s[i:i+2], 16))
    return bytes(result)


def bcd_to_int(data: bytes) -> int:
    """Wandelt BCD-Bytes in eine Ganzzahl um."""
    return int(data.hex())


def format_hex(data: bytes) -> str:
    """Formatiert Bytes als Hex-String."""
    return " ".join(f"{b:02X}" for b in data)


# ZVT Kommando-Codes
ZVT_COMMANDS = {
    (0x06, 0x00): "Registrierung",
    (0x06, 0x01): "Autorisierung (Zahlung)",
    (0x06, 0x30): "Storno",
    (0x06, 0x50): "Kassenschnitt",
    (0x05, 0x01): "Statusabfrage",
    (0x06, 0xB0): "Abbruch",
    (0x06, 0x70): "Diagnose",
    (0x06, 0x02): "Abmeldung",
    (0x80, 0x00): "ACK",
    (0x06, 0x0F): "Abschluss (Completion)",
    (0x06, 0x1E): "Abbruch (Abort)",
    (0x04, 0x0F): "Status-Info",
    (0x04, 0xFF): "Zwischenstatus",
    (0x06, 0xD1): "Druckzeile",
}


def decode_command_name(data: bytes) -> str:
    """Gibt den Namen eines ZVT-Kommandos zurueck."""
    if len(data) < 2:
        return "Unbekannt"
    key = (data[0], data[1])
    return ZVT_COMMANDS.get(key, f"Unbekannt ({data[0]:02X} {data[1]:02X})")


def parse_apdu_length(data: bytes) -> tuple:
    """Parst die Laengenangabe einer APDU. Gibt (daten_laenge, header_laenge) zurueck."""
    if len(data) < 3:
        return 0, 3
    length_byte = data[2]
    if length_byte == 0xFF:
        if len(data) < 5:
            return 0, 5
        return struct.unpack(">H", data[3:5])[0], 5
    return length_byte, 3


def extract_text_from_status(data: bytes) -> str:
    """Versucht lesbaren Text aus einer Zwischenstatus-Nachricht zu extrahieren."""
    # Nach dem Header (Class + Instr + Len) kommen TLV-Daten
    # Text ist oft direkt als ASCII im Datenbereich
    try:
        _, header_len = parse_apdu_length(data)
        payload = data[header_len:]
        # Versuche ASCII-Text zu finden
        text_chars = []
        for b in payload:
            if 0x20 <= b <= 0x7E or b in (0xC4, 0xD6, 0xDC, 0xE4, 0xF6, 0xFC, 0xDF):
                text_chars.append(chr(b))
            elif text_chars:
                break
        return "".join(text_chars).strip()
    except Exception:
        return ""


# ── Kassen-Simulator ──────────────────────────────────────────────

class KassenSimulator:
    """Simuliert eine ZVT-Kasse, die sich mit dem Gateway verbindet."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = None
        self.connected = False

    def connect(self):
        """Verbindet sich mit dem Gateway."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))
            self.connected = True
            print(f"  Verbunden mit Gateway auf {self.host}:{self.port}")
        except Exception as e:
            print(f"  FEHLER: Verbindung fehlgeschlagen: {e}")
            self.connected = False

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.connected = False
            print("  Verbindung getrennt.")

    def send_apdu(self, apdu: bytes):
        """Sendet eine APDU und gibt sie auf der Konsole aus."""
        name = decode_command_name(apdu)
        print(f"\n  >> SENDE: {name}")
        print(f"     Hex: {format_hex(apdu)}")
        msg = build_tcp_message(apdu)
        self.sock.sendall(msg)

    def receive_responses(self, timeout: float = 30.0) -> list:
        """Empfaengt alle Antworten vom Gateway bis Completion/Abort kommt."""
        responses = []
        self.sock.settimeout(timeout)
        done = False

        while not done:
            try:
                # 2-Byte Laenge lesen
                header = self._recv_exact(2)
                if not header:
                    print("  Verbindung vom Gateway geschlossen.")
                    break

                msg_len = struct.unpack(">H", header)[0]
                data = self._recv_exact(msg_len)
                if not data:
                    break

                name = decode_command_name(data)
                print(f"\n  << EMPFANGEN: {name}")
                print(f"     Hex: {format_hex(data)}")

                # Text aus Zwischenstatus extrahieren
                if len(data) >= 2 and data[0] == 0x04 and data[1] == 0xFF:
                    text = extract_text_from_status(data)
                    if text:
                        print(f"     Text: \"{text}\"")

                # Betrag aus Completion extrahieren
                if len(data) >= 2 and data[0] == 0x06 and data[1] == 0x0F:
                    self._print_completion_details(data)

                # Abort-Details
                if len(data) >= 2 and data[0] == 0x06 and data[1] == 0x1E:
                    self._print_abort_details(data)

                responses.append(data)

                # ACK senden fuer jede Antwort (ausser ACK selbst)
                if not (len(data) >= 2 and data[0] == 0x80 and data[1] == 0x00):
                    ack = build_tcp_message(bytes([0x80, 0x00, 0x00]))
                    self.sock.sendall(ack)
                    print("  >> ACK gesendet")

                # Bei Completion oder Abort: fertig
                if len(data) >= 2:
                    if (data[0] == 0x06 and data[1] == 0x0F) or \
                       (data[0] == 0x06 and data[1] == 0x1E) or \
                       (data[0] == 0x80 and data[1] == 0x00):
                        done = True

            except socket.timeout:
                print("  Timeout - keine weitere Antwort.")
                done = True
            except Exception as e:
                print(f"  Fehler beim Empfangen: {e}")
                done = True

        return responses

    def _recv_exact(self, n: int) -> bytes:
        """Empfaengt exakt n Bytes."""
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                return b""
            data += chunk
        return data

    def _print_completion_details(self, data: bytes):
        """Gibt Details einer Completion-Antwort aus."""
        _, header_len = parse_apdu_length(data)
        payload = data[header_len:]
        i = 0
        while i < len(payload):
            tag = payload[i]
            if tag == 0x04 and i + 6 < len(payload):
                amount = bcd_to_int(payload[i+1:i+7])
                print(f"     Betrag: {amount / 100:.2f} EUR")
                i += 7
            elif tag == 0x22 and i + 2 < len(payload):
                print(f"     Kartentyp: {payload[i+1]:02X}")
                i += 3
            else:
                i += 1

    def _print_abort_details(self, data: bytes):
        """Gibt Details einer Abort-Antwort aus."""
        _, header_len = parse_apdu_length(data)
        payload = data[header_len:]
        if payload:
            code = payload[0]
            reasons = {
                0x64: "Keine vorherige Transaktion",
                0x68: "Timeout",
                0x6F: "Zahlung fehlgeschlagen",
                0x83: "SumUp-Verbindungsfehler",
                0xB2: "Nicht unterstuetzter Befehl",
            }
            reason = reasons.get(code, f"Code 0x{code:02X}")
            print(f"     Grund: {reason}")

    # ── ZVT Befehle ──

    def cmd_registration(self):
        """Sendet Registrierung (06 00)."""
        # Config-Byte + Waehrung (EUR = 0x09 0x78) + Service-Byte
        apdu = bytes([0x06, 0x00, 0x06,
                      0x03,        # Config-Byte: PT verwaltet Belege
                      0x09, 0x78,  # Waehrung EUR (0978)
                      0x06, 0x06,  # TLV-Container
                      0x26, 0x01, 0x80,  # Service-Byte
                      ])
        self.send_apdu(apdu)
        return self.receive_responses()

    def cmd_payment(self, amount_cents: int):
        """Sendet Autorisierung/Zahlung (06 01)."""
        amount_bcd = int_to_bcd(amount_cents, 6)
        apdu = bytes([0x06, 0x01, 0x07,
                      0x04]) + amount_bcd + bytes([0x19])  # 0x04=Betrag-Tag, 0x19=Zahlungsart
        self.send_apdu(apdu)
        print(f"     Betrag: {amount_cents / 100:.2f} EUR")
        return self.receive_responses(timeout=130)

    def cmd_reversal(self):
        """Sendet Storno (06 30)."""
        apdu = bytes([0x06, 0x30, 0x00])
        self.send_apdu(apdu)
        return self.receive_responses()

    def cmd_end_of_day(self):
        """Sendet Kassenschnitt (06 50)."""
        apdu = bytes([0x06, 0x50, 0x00])
        self.send_apdu(apdu)
        return self.receive_responses()

    def cmd_status(self):
        """Sendet Statusabfrage (05 01)."""
        apdu = bytes([0x05, 0x01, 0x00])
        self.send_apdu(apdu)
        return self.receive_responses()

    def cmd_diagnosis(self):
        """Sendet Diagnose (06 70)."""
        apdu = bytes([0x06, 0x70, 0x00])
        self.send_apdu(apdu)
        return self.receive_responses()


# ── Terminal-Tester (direkte SumUp API) ───────────────────────────

class TerminalTester:
    """Sendet Zahlungen direkt an das SumUp-Terminal (ohne Gateway)."""

    def __init__(self, config: GatewayConfig):
        self.client = SumUpClient(
            api_key=config.api_key,
            merchant_code=config.merchant_code,
            terminal_id=config.terminal_id,
            affiliate_key=config.affiliate_key,
            affiliate_app_id=config.affiliate_app_id,
        )
        self.config = config

    def test_connection(self):
        """Testet die SumUp-Verbindung."""
        print("\n  Teste SumUp-Verbindung...")
        result = self.client.test_connection()
        if result["ok"]:
            print(f"  OK - Konto: {result.get('business_name', '?')} ({result.get('merchant_code', '?')})")
            print(f"  Terminal-ID: {self.client.terminal_id or '(nicht konfiguriert)'}")
        else:
            print(f"  FEHLER: {result.get('error', 'Unbekannt')}")
        return result["ok"]

    def list_terminals(self):
        """Listet alle verfuegbaren Terminals."""
        print("\n  Suche Terminals...")
        conn = self.client.test_connection()
        if not conn["ok"]:
            print(f"  FEHLER: {conn.get('error', '?')}")
            return

        terminals = self.client.get_terminals()
        if not terminals:
            print("  Keine Terminals gefunden.")
            return

        print(f"  {len(terminals)} Terminal(s) gefunden:\n")
        for i, t in enumerate(terminals, 1):
            tid = t.get("id", t.get("terminal_id", "?"))
            name = t.get("name", t.get("model", "?"))
            status = t.get("status", "?")
            serial = t.get("serial_number", t.get("device", {}).get("identifier", ""))
            print(f"  {i}. {name}")
            print(f"     ID: {tid}")
            if serial:
                print(f"     Seriennummer: {serial}")
            print(f"     Status: {status}")

    def send_payment(self, amount_cents: int):
        """Sendet eine Zahlung an das Terminal."""
        if not self.client.terminal_id:
            print("  FEHLER: Keine Terminal-ID konfiguriert!")
            return

        amount_eur = amount_cents / 100.0
        print(f"\n  Sende Zahlung: {amount_eur:.2f} EUR an Terminal {self.client.terminal_id}")

        try:
            # Checkout erstellen
            print("  1. Erstelle Checkout...")
            checkout = self.client.create_checkout(
                amount_cents=amount_cents,
                currency=self.config.waehrung,
                description=f"Test-Zahlung {amount_eur:.2f} EUR",
            )
            checkout_id = checkout.get("id", "?")
            print(f"     Checkout-ID: {checkout_id}")

            # An Terminal senden
            print("  2. Sende an Terminal...")
            self.client.process_checkout_on_terminal(checkout_id)
            print("     Zahlung auf Terminal angezeigt - warte auf Kunde...")

            # Warten auf Ergebnis
            print("  3. Warte auf Zahlung (max. 120s)...")
            result = self.client.wait_for_payment(checkout_id)
            status = result.get("status", "UNKNOWN")

            if status == "PAID":
                tx_id = result.get("transaction_id", "?")
                print(f"\n  BEZAHLT!")
                print(f"  Transaktions-ID: {tx_id}")
            else:
                print(f"\n  Status: {status}")
                if result.get("error"):
                    print(f"  Fehler: {result['error']}")

        except SumUpError as e:
            print(f"\n  SumUp-Fehler: {e}")
        except Exception as e:
            print(f"\n  Fehler: {e}")

    def send_refund(self, transaction_id: str):
        """Erstattet eine Transaktion."""
        print(f"\n  Storniere Transaktion {transaction_id}...")
        try:
            result = self.client.refund_transaction(transaction_id)
            print(f"  Erstattung erfolgreich!")
            print(f"  Ergebnis: {result}")
        except SumUpError as e:
            print(f"  SumUp-Fehler: {e}")
        except Exception as e:
            print(f"  Fehler: {e}")


# ── ZVT Gateway Simulator (empfaengt von Kasse) ──────────────────

class GatewaySimulator:
    """Simuliert das Gateway - empfaengt ZVT-Befehle von einer echten Kasse."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.server = None
        self.running = False

    def start(self):
        """Startet den simulierten Gateway-Server."""
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(1)
        self.server.settimeout(1)
        self.running = True

        print(f"\n  Gateway-Simulator lauscht auf {self.host}:{self.port}")
        print("  Warte auf Verbindung von Kasse...")
        print("  (Strg+C zum Beenden)\n")

        while self.running:
            try:
                client, addr = self.server.accept()
                print(f"  Kasse verbunden von {addr[0]}:{addr[1]}")
                self._handle_client(client)
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                break

    def stop(self):
        self.running = False
        if self.server:
            self.server.close()

    def _handle_client(self, client: socket.socket):
        """Behandelt eine Kassen-Verbindung."""
        client.settimeout(60)

        try:
            while self.running:
                # Nachricht empfangen
                header = self._recv_exact(client, 2)
                if not header:
                    print("  Kasse hat Verbindung getrennt.")
                    break

                msg_len = struct.unpack(">H", header)[0]
                data = self._recv_exact(client, msg_len)
                if not data:
                    break

                name = decode_command_name(data)
                print(f"\n  << VON KASSE: {name}")
                print(f"     Hex: {format_hex(data)}")

                # Betrag extrahieren bei Zahlung
                if len(data) >= 2 and data[0] == 0x06 and data[1] == 0x01:
                    self._handle_payment(client, data)
                elif len(data) >= 2 and data[0] == 0x06 and data[1] == 0x00:
                    self._handle_registration(client, data)
                elif len(data) >= 2 and data[0] == 0x06 and data[1] == 0x50:
                    self._handle_end_of_day(client, data)
                elif len(data) >= 2 and data[0] == 0x06 and data[1] == 0x30:
                    self._handle_reversal(client, data)
                elif len(data) >= 2 and data[0] == 0x05 and data[1] == 0x01:
                    self._handle_status(client, data)
                else:
                    # ACK senden
                    self._send_ack(client)

        except socket.timeout:
            print("  Timeout - Kasse inaktiv.")
        except Exception as e:
            print(f"  Fehler: {e}")
        finally:
            client.close()
            print("  Kassen-Verbindung geschlossen.")
            print("  Warte auf naechste Verbindung...\n")

    def _handle_registration(self, client: socket.socket, data: bytes):
        """Registrierung: ACK senden, dann Completion."""
        self._send_ack(client)
        self._wait_for_ack(client)
        # Completion senden
        completion = bytes([0x06, 0x0F, 0x00])
        self._send_response(client, completion)
        print("  >> Registrierung bestaetigt")

    def _handle_payment(self, client: socket.socket, data: bytes):
        """Zahlung: Betrag anzeigen und auf Benutzer-Eingabe warten."""
        # Betrag extrahieren
        amount_cents = 0
        _, header_len = parse_apdu_length(data)
        payload = data[header_len:]
        i = 0
        while i < len(payload):
            if payload[i] == 0x04 and i + 6 < len(payload):
                amount_cents = bcd_to_int(payload[i+1:i+7])
                break
            i += 1

        amount_eur = amount_cents / 100.0

        # ACK senden
        self._send_ack(client)
        self._wait_for_ack(client)

        print(f"\n  *** ZAHLUNGSANFORDERUNG: {amount_eur:.2f} EUR ***")
        print()
        print("  Antwort waehlen:")
        print("    1 = Bezahlt (Completion)")
        print("    2 = Abgelehnt (Abort)")
        print("    3 = Timeout")

        choice = input("\n  Eingabe [1/2/3]: ").strip()

        if choice == "1":
            # Completion mit Betrag
            amount_bcd = int_to_bcd(amount_cents, 6)
            trace_bcd = int_to_bcd(int(time.time()) % 999999, 3)
            completion = bytes([0x06, 0x0F]) + bytes([0x0C]) + \
                bytes([0x04]) + amount_bcd + \
                bytes([0x0B]) + trace_bcd + \
                bytes([0x22, 0x02])  # Kartentyp
            self._send_response(client, completion)
            print(f"  >> Zahlung bestaetigt: {amount_eur:.2f} EUR")

        elif choice == "2":
            # Abort
            abort = bytes([0x06, 0x1E, 0x01, 0x6F])  # 0x6F = fehlgeschlagen
            self._send_response(client, abort)
            print("  >> Zahlung abgelehnt")

        else:
            # Timeout
            abort = bytes([0x06, 0x1E, 0x01, 0x68])  # 0x68 = Timeout
            self._send_response(client, abort)
            print("  >> Timeout gesendet")

    def _handle_reversal(self, client: socket.socket, data: bytes):
        """Storno."""
        self._send_ack(client)
        self._wait_for_ack(client)

        print("\n  *** STORNO-ANFORDERUNG ***")
        print("    1 = Storno erfolgreich")
        print("    2 = Storno abgelehnt")
        choice = input("\n  Eingabe [1/2]: ").strip()

        if choice == "1":
            completion = bytes([0x06, 0x0F, 0x00])
            self._send_response(client, completion)
            print("  >> Storno bestaetigt")
        else:
            abort = bytes([0x06, 0x1E, 0x01, 0x6F])
            self._send_response(client, abort)
            print("  >> Storno abgelehnt")

    def _handle_end_of_day(self, client: socket.socket, data: bytes):
        """Kassenschnitt."""
        self._send_ack(client)
        self._wait_for_ack(client)
        completion = bytes([0x06, 0x0F, 0x00])
        self._send_response(client, completion)
        print("  >> Kassenschnitt bestaetigt")

    def _handle_status(self, client: socket.socket, data: bytes):
        """Statusabfrage."""
        self._send_ack(client)
        self._wait_for_ack(client)
        completion = bytes([0x06, 0x0F, 0x00])
        self._send_response(client, completion)
        print("  >> Status OK gesendet")

    def _send_ack(self, client: socket.socket):
        """Sendet ACK."""
        msg = build_tcp_message(bytes([0x80, 0x00, 0x00]))
        client.sendall(msg)

    def _send_response(self, client: socket.socket, apdu: bytes):
        """Sendet eine Antwort und wartet auf ACK."""
        msg = build_tcp_message(apdu)
        client.sendall(msg)
        self._wait_for_ack(client)

    def _wait_for_ack(self, client: socket.socket):
        """Wartet auf ACK von der Kasse."""
        try:
            header = self._recv_exact(client, 2)
            if header:
                msg_len = struct.unpack(">H", header)[0]
                self._recv_exact(client, msg_len)
        except Exception:
            pass

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return b""
            data += chunk
        return data


# ── Hauptmenue ────────────────────────────────────────────────────

def menu_kassen_simulator(config: GatewayConfig):
    """Menue: Kassen-Simulator (sendet ZVT an Gateway)."""
    host = config.tcp_host
    port = config.tcp_port
    sim = KassenSimulator(host, port)

    while True:
        print("\n" + "=" * 50)
        print("  KASSEN-SIMULATOR (ZVT -> Gateway)")
        print("=" * 50)
        print(f"  Gateway: {host}:{port}")
        print(f"  Status: {'Verbunden' if sim.connected else 'Getrennt'}")
        print()
        print("  1) Verbinden")
        print("  2) Registrierung senden (06 00)")
        print("  3) Zahlung senden (06 01)")
        print("  4) Storno senden (06 30)")
        print("  5) Kassenschnitt senden (06 50)")
        print("  6) Statusabfrage (05 01)")
        print("  7) Diagnose (06 70)")
        print("  8) Trennen")
        print("  0) Zurueck")

        choice = input("\n  Auswahl: ").strip()

        if choice == "0":
            sim.disconnect()
            break
        elif choice == "1":
            sim.connect()
        elif choice == "2":
            if not sim.connected:
                print("  Bitte zuerst verbinden!")
                continue
            sim.cmd_registration()
        elif choice == "3":
            if not sim.connected:
                print("  Bitte zuerst verbinden!")
                continue
            betrag = input("  Betrag in EUR (z.B. 1.50): ").strip()
            try:
                cents = int(float(betrag) * 100)
                if cents <= 0:
                    print("  Betrag muss groesser als 0 sein!")
                    continue
                sim.cmd_payment(cents)
            except ValueError:
                print("  Ungueltiger Betrag!")
        elif choice == "4":
            if not sim.connected:
                print("  Bitte zuerst verbinden!")
                continue
            sim.cmd_reversal()
        elif choice == "5":
            if not sim.connected:
                print("  Bitte zuerst verbinden!")
                continue
            sim.cmd_end_of_day()
        elif choice == "6":
            if not sim.connected:
                print("  Bitte zuerst verbinden!")
                continue
            sim.cmd_status()
        elif choice == "7":
            if not sim.connected:
                print("  Bitte zuerst verbinden!")
                continue
            sim.cmd_diagnosis()
        elif choice == "8":
            sim.disconnect()


def menu_gateway_simulator(config: GatewayConfig):
    """Menue: Gateway-Simulator (empfaengt ZVT von echter Kasse)."""
    host = config.tcp_host
    port = config.tcp_port

    print(f"\n  ACHTUNG: Das echte Gateway darf nicht gleichzeitig laufen!")
    print(f"  Port {port} muss frei sein.\n")

    confirm = input("  Fortfahren? (j/n): ").strip().lower()
    if confirm != "j":
        return

    sim = GatewaySimulator(host, port)
    try:
        sim.start()
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()
        print("\n  Gateway-Simulator beendet.")


def menu_terminal_tester(config: GatewayConfig):
    """Menue: Direkter Terminal-Test ueber SumUp API."""
    tester = TerminalTester(config)

    while True:
        print("\n" + "=" * 50)
        print("  TERMINAL-TESTER (direkte SumUp API)")
        print("=" * 50)
        print(f"  Terminal-ID: {config.terminal_id or '(nicht konfiguriert)'}")
        print()
        print("  1) Verbindung testen")
        print("  2) Terminals auflisten")
        print("  3) Zahlung an Terminal senden")
        print("  4) Transaktion stornieren")
        print("  0) Zurueck")

        choice = input("\n  Auswahl: ").strip()

        if choice == "0":
            break
        elif choice == "1":
            tester.test_connection()
        elif choice == "2":
            tester.list_terminals()
        elif choice == "3":
            betrag = input("  Betrag in EUR (z.B. 1.50): ").strip()
            try:
                cents = int(float(betrag) * 100)
                if cents <= 0:
                    print("  Betrag muss groesser als 0 sein!")
                    continue
                tester.send_payment(cents)
            except ValueError:
                print("  Ungueltiger Betrag!")
        elif choice == "4":
            tx_id = input("  Transaktions-ID: ").strip()
            if tx_id:
                tester.send_refund(tx_id)


def main():
    config = GatewayConfig()

    while True:
        print("\n" + "=" * 50)
        print("  ZVT / SumUp TEST-TOOL")
        print("=" * 50)
        print()
        print("  1) Kassen-Simulator")
        print("     Simuliert eine Kasse, sendet ZVT-Befehle")
        print("     an das laufende Gateway")
        print()
        print("  2) Gateway-Simulator")
        print("     Simuliert das Gateway, empfaengt ZVT-Befehle")
        print("     von einer echten Kasse und zeigt sie an.")
        print("     Manuelle Antworten (bezahlt/abgelehnt)")
        print()
        print("  3) Terminal-Tester")
        print("     Sendet Zahlungen direkt an das SumUp-Terminal")
        print("     ueber die Cloud-API (ohne Gateway/ZVT)")
        print()
        print("  0) Beenden")

        choice = input("\n  Auswahl: ").strip()

        if choice == "0":
            print("  Auf Wiedersehen!")
            break
        elif choice == "1":
            menu_kassen_simulator(config)
        elif choice == "2":
            menu_gateway_simulator(config)
        elif choice == "3":
            menu_terminal_tester(config)


if __name__ == "__main__":
    main()
