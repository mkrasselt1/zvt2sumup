"""
ZVT-Server (TCP und COM-Port).

Lauscht auf ZVT-Kommandos vom Kassensystem und leitet sie
an den Gateway-Handler weiter.
"""

import socket
import threading
import logging
import time
from typing import Optional

logger = logging.getLogger("zvt2sumup.server")

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    logger.warning("pyserial nicht installiert - COM-Port-Modus nicht verfuegbar")

from . import zvt_protocol as zvt


class ZVTTCPServer:
    """ZVT-Server ueber TCP/IP (Standard-Port 20007)."""

    def __init__(self, host: str, port: int, handler):
        """
        Args:
            host: Bind-Adresse (z.B. 127.0.0.1)
            port: TCP-Port (Standard: 20007)
            handler: Callback-Funktion fuer empfangene ZVT-Kommandos
        """
        self.host = host
        self.port = port
        self.handler = handler
        self.server_socket = None
        self.running = False
        self._thread = None

    def start(self):
        """Startet den TCP-Server."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(1.0)

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self.running = True
            self._thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._thread.start()
            logger.info(f"ZVT-TCP-Server gestartet auf {self.host}:{self.port}")
        except OSError as e:
            logger.error(f"Server konnte nicht gestartet werden: {e}")
            raise

    def stop(self):
        """Stoppt den TCP-Server."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("ZVT-TCP-Server gestoppt")

    def _accept_loop(self):
        """Akzeptiert eingehende Verbindungen."""
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                logger.info(f"Neue Verbindung von {addr[0]}:{addr[1]}")
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, addr),
                    daemon=True,
                )
                client_thread.start()
            except socket.timeout:
                continue
            except OSError:
                if self.running:
                    logger.error("Fehler beim Akzeptieren der Verbindung")
                break

    def _handle_client(self, sock: socket.socket, addr: tuple):
        """Verarbeitet eine Client-Verbindung."""
        sock.settimeout(30.0)

        try:
            while self.running:
                raw = zvt.read_tcp_message(sock)
                if raw is None:
                    logger.info(f"Verbindung geschlossen: {addr[0]}:{addr[1]}")
                    break

                command = zvt.parse_tcp_apdu(raw)
                if command is None:
                    logger.warning(f"Ungueltiges APDU empfangen: {raw.hex()}")
                    # ACK senden trotzdem
                    sock.sendall(zvt.build_tcp_message(zvt.ZVTResponse.ack()))
                    continue

                # ACK senden
                sock.sendall(zvt.build_tcp_message(zvt.ZVTResponse.ack()))

                # Kommando verarbeiten
                responses = self.handler(command)

                # Antworten senden
                for response_apdu in responses:
                    sock.sendall(zvt.build_tcp_message(response_apdu))
                    # Auf ACK vom Kassensystem warten
                    ack_raw = zvt.read_tcp_message(sock)
                    if ack_raw:
                        ack_cmd = zvt.parse_tcp_apdu(ack_raw)
                        if ack_cmd and ack_cmd.command_id == (0x80, 0x00):
                            logger.debug("ACK vom Kassensystem empfangen")
                        else:
                            logger.warning(f"Unerwartete Antwort statt ACK: {ack_raw.hex()}")

        except socket.timeout:
            logger.info(f"Timeout: {addr[0]}:{addr[1]}")
        except (ConnectionError, OSError) as e:
            logger.debug(f"Verbindungsfehler: {e}")
        finally:
            try:
                sock.close()
            except OSError:
                pass


class ZVTSerialServer:
    """ZVT-Server ueber serielle Schnittstelle (COM-Port)."""

    def __init__(self, port: str, baudrate: int, handler):
        """
        Args:
            port: COM-Port Name (z.B. COM3)
            baudrate: Baudrate (Standard: 9600 oder 115200)
            handler: Callback fuer empfangene ZVT-Kommandos
        """
        if not HAS_SERIAL:
            raise RuntimeError(
                "pyserial nicht installiert! Bitte ausfuehren: pip install pyserial"
            )
        self.port = port
        self.baudrate = baudrate
        self.handler = handler
        self.serial_conn = None
        self.running = False
        self._thread = None

    def start(self):
        """Oeffnet den COM-Port und startet den Empfang."""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,
            )
            self.running = True
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            logger.info(f"ZVT-COM-Server gestartet auf {self.port} ({self.baudrate} Baud)")
        except serial.SerialException as e:
            logger.error(f"COM-Port {self.port} konnte nicht geoeffnet werden: {e}")
            raise

    def stop(self):
        """Schliesst den COM-Port."""
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("ZVT-COM-Server gestoppt")

    def _read_loop(self):
        """Liest kontinuierlich vom COM-Port."""
        buffer = bytearray()

        while self.running:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    buffer.extend(data)

                    # Versuche einen kompletten Frame zu extrahieren
                    frame = self._extract_frame(buffer)
                    if frame:
                        command = zvt.parse_serial_frame(frame)
                        if command:
                            # ACK senden
                            self.serial_conn.write(zvt.build_serial_ack())

                            # Kommando verarbeiten
                            responses = self.handler(command)

                            # Antworten senden
                            for response_apdu in responses:
                                serial_frame = zvt.build_serial_frame(response_apdu)
                                self.serial_conn.write(serial_frame)
                                # Kurze Pause fuer ACK vom Kassensystem
                                time.sleep(0.1)
                                if self.serial_conn.in_waiting > 0:
                                    ack_data = self.serial_conn.read(self.serial_conn.in_waiting)
                                    logger.debug(f"ACK empfangen: {ack_data.hex()}")
                else:
                    time.sleep(0.05)

            except serial.SerialException as e:
                if self.running:
                    logger.error(f"COM-Port Fehler: {e}")
                    time.sleep(1.0)
            except Exception as e:
                logger.error(f"Unerwarteter Fehler: {e}")
                time.sleep(0.5)

    def _extract_frame(self, buffer: bytearray) -> Optional[bytes]:
        """Extrahiert einen kompletten DLE/STX Frame aus dem Buffer."""
        # Suche DLE STX
        start = -1
        for i in range(len(buffer) - 1):
            if buffer[i] == zvt.DLE and buffer[i + 1] == zvt.STX:
                start = i
                break

        if start < 0:
            # Kein Frame-Start gefunden, Buffer aufraumen
            if len(buffer) > 1:
                del buffer[:len(buffer) - 1]
            return None

        # Suche DLE ETX (nicht-gestufft)
        i = start + 2
        while i < len(buffer) - 1:
            if buffer[i] == zvt.DLE:
                if buffer[i + 1] == zvt.ETX:
                    # Frame gefunden (+ 1 Byte CRC)
                    end = i + 3
                    if end <= len(buffer):
                        frame = bytes(buffer[start:end])
                        del buffer[:end]
                        return frame
                    else:
                        return None  # CRC noch nicht empfangen
                elif buffer[i + 1] == zvt.DLE:
                    i += 2  # DLE-Stuffing ueberspringen
                    continue
            i += 1

        # Noch kein kompletter Frame
        # Buffer-Overflow-Schutz
        if len(buffer) > 4096:
            logger.warning("Buffer-Overflow, verwerfe Daten")
            buffer.clear()

        return None
