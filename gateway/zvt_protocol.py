"""
ZVT-Protokoll-Handler (Zahlungsverkehrstechnik).

Implementiert das ZVT-Protokoll nach ZVT-Kassenprotokoll (Version 700)
fuer die Kommunikation zwischen Kassensystem und diesem Gateway.

Unterstuetzte Kommandos:
- 06 00: Registrierung (Registration)
- 06 01: Autorisierung / Zahlung (Authorization)
- 06 30: Storno (Reversal)
- 06 50: Kassenschnitt / Tagesabschluss (End of Day)
- 05 01: Statusabfrage (Status Enquiry)
- 06 B0: Abbruch (Abort)
"""

import struct
import logging
from enum import IntEnum
from typing import Optional

logger = logging.getLogger("zvt2sumup.zvt")


# ── ZVT Kommando-Klassen ──────────────────────────────────────────────

class ZVTCommand:
    """Repraesentiert ein ZVT-APDU-Kommando."""

    # Kommando-IDs (Klasse, Instruktion)
    REGISTRATION = (0x06, 0x00)
    AUTHORIZATION = (0x06, 0x01)
    REVERSAL = (0x06, 0x30)
    END_OF_DAY = (0x06, 0x50)
    STATUS_ENQUIRY = (0x05, 0x01)
    ABORT = (0x06, 0xB0)
    DIAGNOSIS = (0x06, 0x70)
    LOG_OFF = (0x06, 0x02)

    # Bekannte Kommando-Namen (fuer Logging)
    NAMES = {
        (0x06, 0x00): "Registrierung",
        (0x06, 0x01): "Autorisierung (Zahlung)",
        (0x06, 0x30): "Storno",
        (0x06, 0x50): "Kassenschnitt",
        (0x05, 0x01): "Statusabfrage",
        (0x06, 0xB0): "Abbruch",
        (0x06, 0x70): "Diagnose",
        (0x06, 0x02): "Abmeldung",
    }

    def __init__(self, cmd_class: int, cmd_instr: int, data: bytes = b""):
        self.cmd_class = cmd_class
        self.cmd_instr = cmd_instr
        self.data = data

    @property
    def command_id(self) -> tuple:
        return (self.cmd_class, self.cmd_instr)

    @property
    def name(self) -> str:
        return self.NAMES.get(self.command_id, f"Unbekannt ({self.cmd_class:02X} {self.cmd_instr:02X})")

    def __repr__(self):
        return f"ZVTCommand({self.cmd_class:02X} {self.cmd_instr:02X} '{self.name}' data={self.data.hex()})"


class ZVTResponse:
    """Baut ZVT-Antwort-APDUs."""

    @staticmethod
    def ack() -> bytes:
        """Positive Quittung (80 00)."""
        return ZVTResponse._build_apdu(0x80, 0x00)

    @staticmethod
    def completion(data: bytes = b"") -> bytes:
        """Kommando erfolgreich abgeschlossen (06 0F)."""
        return ZVTResponse._build_apdu(0x06, 0x0F, data)

    @staticmethod
    def abort(result_code: int = 0) -> bytes:
        """Kommando abgebrochen (06 1E)."""
        # TLV: Ergebniscode
        tlv_data = bytes([0x27, 0x01, result_code]) if result_code else b""
        return ZVTResponse._build_apdu(0x06, 0x1E, tlv_data)

    @staticmethod
    def status_info(data: bytes = b"") -> bytes:
        """Statusinformation (04 0F)."""
        return ZVTResponse._build_apdu(0x04, 0x0F, data)

    @staticmethod
    def intermediate_status(status_text: str = "") -> bytes:
        """Zwischenstatus (04 FF) - zeigt Text auf der Kasse an."""
        text_bytes = status_text.encode("latin-1")[:40]  # Max 40 Zeichen
        # TLV Tag 24 = Displaytext
        tlv_data = bytes([0x24, len(text_bytes)]) + text_bytes
        return ZVTResponse._build_apdu(0x04, 0xFF, tlv_data)

    @staticmethod
    def print_line(text: str) -> bytes:
        """Druckzeile (06 D1)."""
        text_bytes = text.encode("latin-1")[:40]
        tlv_data = bytes([0x25, len(text_bytes)]) + text_bytes
        return ZVTResponse._build_apdu(0x06, 0xD1, tlv_data)

    @staticmethod
    def _build_apdu(cmd_class: int, cmd_instr: int, data: bytes = b"") -> bytes:
        return bytes([cmd_class, cmd_instr]) + _encode_length(len(data)) + data


# ── ZVT Transport (TCP) ──────────────────────────────────────────────

def _encode_length(length: int) -> bytes:
    """Kodiert die Laenge im ZVT-Format (1 oder 3 Bytes)."""
    if length < 0xFF:
        return bytes([length])
    else:
        return bytes([0xFF]) + struct.pack(">H", length)


def _decode_length(data: bytes, offset: int) -> tuple:
    """Dekodiert die Laenge. Gibt (laenge, neuer_offset) zurueck."""
    if data[offset] < 0xFF:
        return data[offset], offset + 1
    else:
        length = struct.unpack(">H", data[offset + 1:offset + 3])[0]
        return length, offset + 3


def parse_tcp_apdu(raw: bytes) -> Optional[ZVTCommand]:
    """
    Parst ein ZVT-APDU aus TCP-Daten.
    TCP-Format: Laenge (2 Bytes Big-Endian) + APDU
    """
    if len(raw) < 2:
        return None

    try:
        cmd_class = raw[0]
        cmd_instr = raw[1]

        if len(raw) > 2:
            data_len, data_start = _decode_length(raw, 2)
            data = raw[data_start:data_start + data_len]
        else:
            data = b""

        cmd = ZVTCommand(cmd_class, cmd_instr, data)
        logger.debug(f"ZVT empfangen: {cmd}")
        return cmd

    except (IndexError, struct.error) as e:
        logger.error(f"Fehler beim Parsen des ZVT-APDU: {e} (Daten: {raw.hex()})")
        return None


def read_tcp_message(sock) -> Optional[bytes]:
    """
    Liest eine komplette ZVT-TCP-Nachricht.
    Format: 2 Bytes Laenge (Big-Endian) + Nutzdaten.
    """
    try:
        header = _recv_exact(sock, 2)
        if not header:
            return None

        msg_len = struct.unpack(">H", header)[0]
        if msg_len == 0:
            return None

        payload = _recv_exact(sock, msg_len)
        if not payload:
            return None

        return payload

    except (ConnectionError, OSError) as e:
        logger.debug(f"Verbindungsfehler beim Lesen: {e}")
        return None


def build_tcp_message(apdu: bytes) -> bytes:
    """Verpackt ein APDU fuer den TCP-Transport (2 Byte Laenge + APDU)."""
    return struct.pack(">H", len(apdu)) + apdu


def _recv_exact(sock, n: int) -> Optional[bytes]:
    """Empfaengt exakt n Bytes vom Socket."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


# ── ZVT Transport (Seriell / COM-Port) ───────────────────────────────

# Steuerzeichen
DLE = 0x10
STX = 0x02
ETX = 0x03
ACK = 0x06
NAK = 0x15


def parse_serial_frame(raw: bytes) -> Optional[ZVTCommand]:
    """
    Parst ein ZVT-APDU aus einem seriellen Frame.
    Format: DLE STX APDU DLE ETX CRC
    """
    if len(raw) < 6:
        return None

    try:
        # Frame: DLE STX ... DLE ETX LRC
        if raw[0] != DLE or raw[1] != STX:
            logger.warning(f"Ungueltiger Frame-Start: {raw[:2].hex()}")
            return None

        # Finde DLE ETX (Ende)
        apdu_data = bytearray()
        i = 2
        while i < len(raw) - 2:
            if raw[i] == DLE:
                if raw[i + 1] == ETX:
                    break
                elif raw[i + 1] == DLE:
                    # DLE-Stuffing: doppeltes DLE = ein DLE
                    apdu_data.append(DLE)
                    i += 2
                    continue
            apdu_data.append(raw[i])
            i += 1

        return parse_tcp_apdu(bytes(apdu_data))

    except (IndexError, struct.error) as e:
        logger.error(f"Fehler beim Parsen des seriellen Frames: {e}")
        return None


def build_serial_frame(apdu: bytes) -> bytes:
    """Verpackt ein APDU fuer den seriellen Transport (DLE/STX Framing + CRC)."""
    frame = bytearray([DLE, STX])

    # DLE-Stuffing: jedes DLE in den Daten verdoppeln
    for byte in apdu:
        frame.append(byte)
        if byte == DLE:
            frame.append(DLE)

    frame.extend([DLE, ETX])

    # LRC-Pruefsumme (XOR ueber alles zwischen STX und ETX inkl.)
    lrc = 0
    for b in apdu:
        lrc ^= b
    lrc ^= ETX
    frame.append(lrc)

    return bytes(frame)


def build_serial_ack() -> bytes:
    """Baut ein serielles ACK (DLE ACK)."""
    return bytes([DLE, ACK])


# ── BCD-Hilfsfunktionen ──────────────────────────────────────────────

def bcd_to_int(data: bytes) -> int:
    """Konvertiert BCD-kodierte Bytes zu einer Ganzzahl."""
    result = 0
    for byte in data:
        result = result * 100 + ((byte >> 4) * 10) + (byte & 0x0F)
    return result


def int_to_bcd(value: int, num_bytes: int) -> bytes:
    """Konvertiert eine Ganzzahl zu BCD-kodierten Bytes."""
    result = bytearray(num_bytes)
    for i in range(num_bytes - 1, -1, -1):
        result[i] = ((value % 10) | ((value // 10 % 10) << 4))
        value //= 100
    return bytes(result)


def extract_amount(data: bytes) -> Optional[int]:
    """
    Extrahiert den Betrag aus ZVT-APDU-Daten.
    Tag 0x04 = Betrag in Cent (6 Bytes BCD).
    """
    i = 0
    while i < len(data):
        tag = data[i]
        i += 1

        if tag == 0x04:
            # Betrag: 6 Bytes BCD
            if i + 6 <= len(data):
                amount = bcd_to_int(data[i:i + 6])
                return amount
            return None

        # Einfache TLV-Navigation (1-Byte Tags)
        if tag == 0x06:  # TLV-Container
            if i < len(data):
                i += data[i] + 1
        elif tag in (0x19, 0x29, 0x49, 0x60):
            if i < len(data):
                i += data[i] + 1
        else:
            # Bekannte feste Laengen
            fixed_lengths = {
                0x04: 6, 0x0B: 3, 0x0C: 3, 0x0D: 1, 0x17: 2,
                0x22: 2, 0x27: 1, 0x29: 0, 0x2A: 15, 0x2D: 2,
                0x37: 3, 0x3B: 8, 0x3C: 1, 0x87: 2, 0x88: 3,
            }
            if tag in fixed_lengths:
                i += fixed_lengths[tag]
            else:
                break

    return None
