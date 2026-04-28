"""
Grafische Einrichtung (Setup-Assistent) fuer das ZVT-SumUp-Gateway.

Einfaches Tkinter-GUI zum Konfigurieren der config.ini.
Wird beim ersten Start oder ueber setup.bat aufgerufen.
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gateway.config import GatewayConfig
from gateway.sumup_api import SumUpClient


class SetupAssistent(tk.Tk):
    """Grafischer Einrichtungsassistent."""

    def __init__(self):
        super().__init__()
        self.title("ZVT-zu-SumUp Gateway - Einrichtung")
        self.geometry("580x660")
        self.resizable(False, False)
        self.config_data = GatewayConfig()
        self._terminals_cache = []  # Gefundene Terminals
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        """Erstellt die Oberflaeche."""
        # Hauptframe mit Padding
        main = ttk.Frame(self, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # Titel
        title = ttk.Label(main, text="ZVT-zu-SumUp Gateway Einrichtung",
                          font=("Segoe UI", 14, "bold"))
        title.pack(pady=(0, 5))

        subtitle = ttk.Label(main,
                             text="Bitte geben Sie Ihre SumUp-Zugangsdaten ein.",
                             font=("Segoe UI", 9))
        subtitle.pack(pady=(0, 15))

        # ── SumUp-Einstellungen ───────────────────────────────
        sumup_frame = ttk.LabelFrame(main, text=" SumUp-Zugangsdaten ", padding=10)
        sumup_frame.pack(fill=tk.X, pady=(0, 10))

        # API-Key
        ttk.Label(sumup_frame, text="API-Schluessel:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.api_key_var = tk.StringVar()
        api_entry = ttk.Entry(sumup_frame, textvariable=self.api_key_var, width=50, show="*")
        api_entry.grid(row=0, column=1, columnspan=2, padx=(10, 0), pady=3, sticky=tk.W)

        ttk.Label(sumup_frame, text="(SumUp Dashboard > Entwickler > API-Schluessel)",
                  font=("Segoe UI", 7)).grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=(10, 0))

        # Konto-Info (wird automatisch geladen)
        ttk.Label(sumup_frame, text="Konto:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.account_label = ttk.Label(sumup_frame, text="(wird automatisch erkannt)",
                                       font=("Segoe UI", 9), foreground="gray")
        self.account_label.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=(10, 0), pady=3)

        # Terminal-ID als Dropdown
        ttk.Label(sumup_frame, text="Terminal:").grid(row=3, column=0, sticky=tk.W, pady=3)

        terminal_row = ttk.Frame(sumup_frame)
        terminal_row.grid(row=3, column=1, columnspan=2, padx=(10, 0), pady=3, sticky=tk.W)

        self.terminal_var = tk.StringVar()
        self.terminal_combo = ttk.Combobox(terminal_row, textvariable=self.terminal_var,
                                           width=40, state="readonly")
        self.terminal_combo.pack(side=tk.LEFT)

        self.terminal_refresh_btn = ttk.Button(terminal_row, text="Terminals laden",
                                               command=self._load_terminals)
        self.terminal_refresh_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.terminal_status = ttk.Label(sumup_frame, text="", font=("Segoe UI", 7))
        self.terminal_status.grid(row=4, column=1, columnspan=2, sticky=tk.W, padx=(10, 0))

        # Test-Button
        self.test_btn = ttk.Button(sumup_frame, text="Verbindung testen",
                                   command=self._test_connection)
        self.test_btn.grid(row=5, column=1, columnspan=2, sticky=tk.E, pady=(10, 0))

        self.test_label = ttk.Label(sumup_frame, text="", font=("Segoe UI", 9))
        self.test_label.grid(row=5, column=0, sticky=tk.W, pady=(10, 0))

        # ── Gateway-Einstellungen ─────────────────────────────
        gw_frame = ttk.LabelFrame(main, text=" Gateway-Einstellungen ", padding=10)
        gw_frame.pack(fill=tk.X, pady=(0, 10))

        # Modus
        ttk.Label(gw_frame, text="Verbindungsmodus:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.modus_var = tk.StringVar(value="tcp")
        modus_frame = ttk.Frame(gw_frame)
        modus_frame.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        ttk.Radiobutton(modus_frame, text="TCP/IP (empfohlen)", variable=self.modus_var,
                        value="tcp", command=self._on_modus_change).pack(side=tk.LEFT)
        ttk.Radiobutton(modus_frame, text="COM-Port (seriell)", variable=self.modus_var,
                        value="com", command=self._on_modus_change).pack(side=tk.LEFT, padx=(15, 0))

        # TCP-Einstellungen
        self.tcp_frame = ttk.Frame(gw_frame)
        self.tcp_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Label(self.tcp_frame, text="TCP-Port:").grid(row=0, column=0, sticky=tk.W)
        self.tcp_port_var = tk.StringVar(value="20007")
        ttk.Entry(self.tcp_frame, textvariable=self.tcp_port_var, width=10).grid(
            row=0, column=1, padx=(10, 0))
        ttk.Label(self.tcp_frame, text="(Standard: 20007)",
                  font=("Segoe UI", 7)).grid(row=0, column=2, padx=(10, 0))

        # COM-Einstellungen
        self.com_frame = ttk.Frame(gw_frame)

        ttk.Label(self.com_frame, text="COM-Port:").grid(row=0, column=0, sticky=tk.W)
        self.com_port_var = tk.StringVar(value="COM3")
        ttk.Entry(self.com_frame, textvariable=self.com_port_var, width=10).grid(
            row=0, column=1, padx=(10, 0))

        ttk.Label(self.com_frame, text="Baudrate:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.com_baud_var = tk.StringVar(value="9600")
        baud_combo = ttk.Combobox(self.com_frame, textvariable=self.com_baud_var,
                                  values=["9600", "19200", "38400", "57600", "115200"],
                                  width=8, state="readonly")
        baud_combo.grid(row=1, column=1, padx=(10, 0), pady=3)

        # ── Buttons ───────────────────────────────────────────
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(15, 0))

        ttk.Button(btn_frame, text="Speichern und Schliessen",
                   command=self._save).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Abbrechen",
                   command=self.destroy).pack(side=tk.RIGHT, padx=(0, 10))

    def _load_values(self):
        """Laedt aktuelle Werte in die Felder."""
        self.api_key_var.set(self.config_data.api_key)
        self.modus_var.set(self.config_data.modus)
        self.tcp_port_var.set(str(self.config_data.tcp_port))
        self.com_port_var.set(self.config_data.com_port)
        self.com_baud_var.set(str(self.config_data.com_baudrate))
        self._on_modus_change()

        # Wenn API-Key vorhanden, Konto und Terminals automatisch laden
        saved_tid = self.config_data.terminal_id
        if self.config_data.api_key:
            self._verify_and_load(preselect=saved_tid)
        elif saved_tid:
            self.terminal_combo.configure(state="normal")
            self.terminal_combo.set(saved_tid)
            self.terminal_combo.configure(state="readonly")

    def _on_modus_change(self):
        """Schaltet TCP/COM-Felder um."""
        if self.modus_var.get() == "tcp":
            self.com_frame.grid_remove()
            self.tcp_frame.grid()
        else:
            self.tcp_frame.grid_remove()
            self.com_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5)

    def _verify_and_load(self, preselect: str = ""):
        """Prueft den API-Key, laedt Konto-Info und Terminals in einem Rutsch."""
        api_key = self.api_key_var.get().strip()
        if not api_key:
            return

        self.test_btn.configure(state="disabled")
        self.terminal_refresh_btn.configure(state="disabled")
        self.account_label.configure(text="Pruefe...", foreground="gray")
        self.terminal_status.configure(text="Lade Terminals...", foreground="gray")
        self.update()

        def do_load():
            client = SumUpClient(api_key)
            conn = client.test_connection()
            terminals = client.get_terminals() if conn["ok"] else []
            self.after(0, lambda: self._show_account_and_terminals(conn, terminals, preselect))

        threading.Thread(target=do_load, daemon=True).start()

    def _show_account_and_terminals(self, conn: dict, terminals: list, preselect: str = ""):
        """Zeigt Konto-Info und Terminals an."""
        self.test_btn.configure(state="normal")
        self.terminal_refresh_btn.configure(state="normal")

        if conn["ok"]:
            name = conn.get("business_name", "")
            code = conn.get("merchant_code", "")
            if name and code:
                self.account_label.configure(text=f"{name} ({code})", foreground="green")
            elif code:
                self.account_label.configure(text=code, foreground="green")
            else:
                self.account_label.configure(text="Verbunden", foreground="green")
            self.test_label.configure(text="Verbindung OK!", foreground="green")
            self._show_terminals(terminals, preselect)
        else:
            error = conn.get("error", "Verbindung fehlgeschlagen")
            self.account_label.configure(text=error, foreground="red")
            self.test_label.configure(text="Fehlgeschlagen!", foreground="red")
            self.terminal_status.configure(text="")

    def _load_terminals(self, preselect: str = ""):
        """Laedt die verfuegbaren Terminals von SumUp im Hintergrund."""
        api_key = self.api_key_var.get().strip()

        if not api_key:
            messagebox.showwarning("Fehlende Daten",
                                   "Bitte zuerst den API-Schluessel eingeben.")
            return

        self.terminal_refresh_btn.configure(state="disabled")
        self.terminal_status.configure(text="Lade Terminals...", foreground="gray")
        self.update()

        def do_load():
            client = SumUpClient(api_key)
            # Merchant Code ermitteln (wird fuer get_terminals benoetigt)
            conn = client.test_connection()
            terminals = client.get_terminals() if conn["ok"] else []
            self.after(0, lambda: self._show_terminals(terminals, preselect))

        threading.Thread(target=do_load, daemon=True).start()

    def _show_terminals(self, terminals: list, preselect: str = ""):
        """Zeigt die geladenen Terminals im Dropdown an."""
        self.terminal_refresh_btn.configure(state="normal")
        self._terminals_cache = terminals

        if not terminals:
            self.terminal_combo.configure(values=[])
            self.terminal_combo.set("")
            self.terminal_status.configure(
                text="Keine Terminals gefunden. Ist Ihr SumUp Solo eingerichtet?",
                foreground="red",
            )
            return

        # Dropdown-Eintraege bauen: "Terminal-Name (ID)"
        entries = []
        for t in terminals:
            tid = t.get("id", t.get("terminal_id", ""))
            name = t.get("name", t.get("model", "Terminal"))
            serial = t.get("serial_number", "")
            label = f"{name} - {serial} ({tid})" if serial else f"{name} ({tid})"
            entries.append(label)

        self.terminal_combo.configure(values=entries)

        if len(terminals) == 1:
            # Nur ein Terminal: automatisch auswaehlen
            self.terminal_combo.current(0)
            self.terminal_status.configure(
                text="1 Terminal gefunden - automatisch ausgewaehlt",
                foreground="green",
            )
        else:
            # Mehrere: vorherige Auswahl wiederherstellen oder Hinweis
            matched = False
            if preselect:
                for i, t in enumerate(terminals):
                    tid = t.get("id", t.get("terminal_id", ""))
                    if str(tid) == str(preselect):
                        self.terminal_combo.current(i)
                        matched = True
                        break
            if not matched:
                self.terminal_combo.current(0)

            self.terminal_status.configure(
                text=f"{len(terminals)} Terminals gefunden - bitte auswaehlen",
                foreground="blue",
            )

    def _get_selected_terminal_id(self) -> str:
        """Extrahiert die Terminal-ID aus dem Dropdown-Text."""
        selected = self.terminal_var.get().strip()
        if not selected:
            return ""

        # Format: "Name - Serial (ID)" oder "Name (ID)" -> ID extrahieren
        if "(" in selected and selected.endswith(")"):
            return selected.rsplit("(", 1)[1].rstrip(")")

        return selected

    def _test_connection(self):
        """Testet die SumUp-Verbindung im Hintergrund (laedt alles neu)."""
        api_key = self.api_key_var.get().strip()

        if not api_key:
            messagebox.showwarning("Fehlende Daten",
                                   "Bitte den API-Schluessel eingeben.")
            return

        saved_tid = self._get_selected_terminal_id()
        self._verify_and_load(preselect=saved_tid)

    def _save(self):
        """Speichert die Konfiguration."""
        terminal_id = self._get_selected_terminal_id()

        # Merchant Code aus dem Account-Label extrahieren (wurde automatisch ermittelt)
        account_text = self.account_label.cget("text")
        merchant_code = ""
        if "(" in account_text and account_text.endswith(")"):
            merchant_code = account_text.rsplit("(", 1)[1].rstrip(")")
        elif account_text and account_text not in ("(wird automatisch erkannt)", "Verbunden", "Pruefe..."):
            merchant_code = account_text

        # Werte uebernehmen
        self.config_data.set("sumup", "api_key", self.api_key_var.get().strip())
        self.config_data.set("sumup", "merchant_code", merchant_code)
        self.config_data.set("sumup", "terminal_id", terminal_id)
        self.config_data.set("gateway", "modus", self.modus_var.get())
        self.config_data.set("gateway", "tcp_port", self.tcp_port_var.get().strip())
        self.config_data.set("gateway", "com_port", self.com_port_var.get().strip())
        self.config_data.set("gateway", "com_baudrate", self.com_baud_var.get().strip())

        # Validieren
        errors = self.config_data.validate()
        if errors:
            messagebox.showerror("Konfigurationsfehler",
                                 "Bitte korrigieren Sie:\n\n" + "\n".join(f"- {e}" for e in errors))
            return

        # Warnung wenn kein Terminal
        if not terminal_id:
            result = messagebox.askokcancel(
                "Kein Terminal ausgewaehlt",
                "Ohne Terminal-ID kann das Gateway keine Zahlungen\n"
                "an Ihr SumUp Solo senden.\n\n"
                "Trotzdem speichern?",
            )
            if not result:
                return

        # Speichern
        self.config_data.save()
        messagebox.showinfo("Gespeichert",
                            "Konfiguration wurde gespeichert.\n\n"
                            "Sie koennen das Gateway jetzt mit start.bat starten.")
        self.destroy()


def main():
    app = SetupAssistent()
    app.mainloop()


if __name__ == "__main__":
    main()
