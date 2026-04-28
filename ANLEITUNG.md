# ZVT-zu-SumUp Gateway

## Was ist das?

Dieses Programm ist eine **Bruecke** (Gateway) zwischen einem klassischen **Kassensystem** (POS), das das deutsche **ZVT-Protokoll** spricht, und einem modernen **SumUp Solo** Kartenterminal.

### Das Problem

Viele Kassensysteme in Deutschland (z.B. Vectron, Gastrofix, Lightspeed, etc.) kommunizieren mit Kartenterminals ueber das **ZVT-Protokoll** (Zahlungsverkehrstechnik). Das ist der deutsche Standard fuer EC-/Kreditkartenzahlung am Point of Sale.

Das **SumUp Solo** Terminal unterstuetzt dieses Protokoll jedoch **nicht** - es ist ein cloudbasiertes Terminal mit eigener API.

### Die Loesung

Dieses Gateway:

1. **Lauscht** auf ZVT-Kommandos von Ihrem Kassensystem (ueber TCP/IP oder virtuellen COM-Port)
2. **Uebersetzt** diese Kommandos in SumUp-API-Aufrufe
3. **Sendet** die Zahlung an Ihr SumUp Solo Terminal
4. **Wartet** auf das Ergebnis (Kunde bezahlt am Terminal)
5. **Antwortet** dem Kassensystem im ZVT-Format ("Zahlung erfolgreich" / "Zahlung abgelehnt")

```
┌──────────────┐     ZVT      ┌─────────────┐    HTTPS     ┌───────────┐
│ Kassensystem │ ───────────> │   Gateway   │ ──────────> │ SumUp API │
│   (POS)      │ <─────────── │ (dieses     │ <────────── │  (Cloud)  │
│              │     ZVT      │  Programm)  │    HTTPS    │           │
└──────────────┘              └─────────────┘             └─────┬─────┘
                                                                │
                                                           ┌────▼─────┐
                                                           │  SumUp   │
                                                           │   Solo   │
                                                           │ Terminal │
                                                           └──────────┘
```

---

## Voraussetzungen

- **Windows 10 oder 11**
- **Internetverbindung** (das Gateway kommuniziert mit der SumUp-Cloud)
- **SumUp-Geschaeftskonto** mit API-Zugang
- **SumUp Solo Terminal** (eingerichtet und mit Ihrem Konto verbunden)
- **Kassensystem** mit ZVT-Unterstuetzung (TCP/IP oder seriell)

---

## Installation (3 Schritte)

### Schritt 1: install.bat ausfuehren

Doppelklick auf **`install.bat`** - das Skript:
- Prueft ob Python installiert ist (installiert es bei Bedarf)
- Installiert die benoetigten Pakete
- Erstellt die Konfigurationsdatei
- Legt eine Desktop-Verknuepfung an

### Schritt 2: SumUp-Zugangsdaten eingeben

Doppelklick auf **`setup.bat`** - es oeffnet sich ein Fenster:

1. **API-Schluessel** eingeben
   - Wo finde ich den? → SumUp Dashboard → Entwickler → API-Schluessel
   - https://me.sumup.com/de-de/developer
2. **Haendler-Code** eingeben
   - Wo finde ich den? → SumUp Dashboard → Konto → Geschaeftsprofil
3. **Terminal-ID** eingeben (optional)
   - Nur noetig wenn Sie mehrere Terminals haben
4. **Verbindungsmodus** waehlen:
   - **TCP/IP** (empfohlen): Port 20007 (ZVT-Standard)
   - **COM-Port**: Fuer aeltere Kassensysteme mit serieller Anbindung
5. Auf "Verbindung testen" klicken
6. "Speichern und Schliessen"

### Schritt 3: Gateway starten

Doppelklick auf **`start.bat`** (oder die Desktop-Verknuepfung).

Das Gateway laeuft jetzt und wartet auf Kommandos vom Kassensystem.

---

## Kassensystem einrichten

### TCP/IP-Modus (empfohlen)

In Ihrem Kassensystem die ZVT-Einstellungen wie folgt setzen:

| Einstellung    | Wert          |
|--------------- |---------------|
| IP-Adresse     | `127.0.0.1`   |
| Port           | `20007`       |
| Protokoll      | ZVT (TCP/IP)  |

> Wenn das Kassensystem auf einem anderen PC laeuft, verwenden Sie die
> IP-Adresse des Gateway-PCs statt 127.0.0.1.

### COM-Port-Modus (seriell)

Fuer den COM-Port-Modus benoetigen Sie einen **virtuellen COM-Port**.

**Einrichtung mit com0com (kostenlos):**

1. com0com herunterladen: https://sourceforge.net/projects/com0com/
2. Installieren und ein Portpaar erstellen (z.B. COM3 ↔ COM4)
3. Im Gateway: COM4 einstellen (in setup.bat)
4. Im Kassensystem: COM3 einstellen

| Einstellung    | Kassensystem  | Gateway       |
|--------------- |---------------|---------------|
| COM-Port       | COM3          | COM4          |
| Baudrate       | 9600          | 9600          |
| Datenbits      | 8             | 8             |
| Paritaet       | Keine         | Keine         |
| Stoppbits      | 1             | 1             |

---

## Unterstuetzte Funktionen

| Funktion             | ZVT-Kommando | Status              |
|----------------------|------------- |---------------------|
| Registrierung        | 06 00        | Unterstuetzt        |
| Kartenzahlung        | 06 01        | Unterstuetzt        |
| Storno               | 06 30        | Unterstuetzt        |
| Kassenschnitt        | 06 50        | Unterstuetzt (Info) |
| Statusabfrage        | 05 01        | Unterstuetzt        |
| Abbruch              | 06 B0        | Unterstuetzt        |
| Diagnose             | 06 70        | Unterstuetzt        |
| Abmeldung            | 06 02        | Unterstuetzt        |

---

## Was das Gateway NICHT kann

Bitte lesen Sie diese Liste aufmerksam:

1. **Kein Offline-Betrieb**
   Das Gateway benoetigt eine aktive Internetverbindung. Ohne Internet keine Kartenzahlung.

2. **Kein Geldkarte/GiroGo**
   SumUp unterstuetzt keine kontaktlosen Geldkarten-Zahlungen (ehemals GiroGo).

3. **Kein vollstaendiger ZVT-Ersatz**
   Nicht alle ZVT-Kommandos sind implementiert. Exotische Kassensystem-Funktionen (z.B. Vorkasse, Trinkgeld ueber ZVT, Waehrungswahl) werden nicht unterstuetzt.

4. **Kein Echtzeit-Kassenschnitt**
   SumUp rechnet automatisch ab. Der Kassenschnitt (Tagesabschluss) liefert eine Zusammenfassung, fuehrt aber keine tatsaechliche Abrechnung durch.

5. **Keine DCC (Dynamic Currency Conversion)**
   Keine automatische Waehrungsumrechnung fuer auslaendische Karten.

6. **Keine zertifizierte Loesung**
   Dieses Gateway ist **nicht** von der Deutschen Kreditwirtschaft oder SumUp offiziell zertifiziert. Es ist ein Community-Projekt.

7. **Keine Haendler-Belege im ZVT-Format**
   Belege werden von SumUp digital erstellt, nicht ueber das ZVT-Druckprotokoll.

---

## Konfigurationsdatei (config.ini)

Die Datei `config.ini` kann auch direkt mit einem Texteditor bearbeitet werden:

```ini
[gateway]
; Verbindungsmodus: tcp oder com
modus = tcp

; TCP-Einstellungen
tcp_port = 20007
tcp_host = 127.0.0.1

; COM-Port-Einstellungen (nur bei modus = com)
com_port = COM3
com_baudrate = 9600

; Waehrung (ISO 4217)
waehrung = EUR

; Logging
log_level = INFO
log_datei = zvt2sumup.log

[sumup]
; SumUp API-Schluessel (Bearer Token)
api_key = HIER_IHR_API_KEY

; SumUp Haendler-Code
merchant_code = HIER_IHR_MERCHANT_CODE

; Terminal-ID (leer = automatisch)
terminal_id =

; Maximale Wartezeit auf Zahlung in Sekunden
zahlung_timeout = 120
```

---

## SumUp API-Schluessel erstellen

1. Gehen Sie zu https://me.sumup.com/de-de/developer
2. Melden Sie sich mit Ihrem SumUp-Geschaeftskonto an
3. Klicken Sie auf "API-Schluessel erstellen"
4. Vergeben Sie einen Namen (z.B. "ZVT Gateway")
5. Berechtigungen setzen:
   - `payments` (Zahlungen)
   - `transactions.history` (Transaktionsverlauf)
   - `user.app-settings` (Kontoeinstellungen)
6. API-Schluessel kopieren und in setup.bat eingeben

> **WICHTIG:** Bewahren Sie den API-Schluessel sicher auf!
> Er ermoeglicht Zugriff auf Ihr SumUp-Konto.

---

## Fehlerbehebung

### "Python nicht gefunden"
→ Python manuell installieren: https://www.python.org/downloads/
→ **WICHTIG:** Bei der Installation den Haken bei "Add Python to PATH" setzen!

### "SumUp-Verbindung fehlgeschlagen"
→ Internetverbindung pruefen
→ API-Schluessel korrekt? (setup.bat erneut ausfuehren)
→ SumUp-Konto aktiv? (https://me.sumup.com pruefen)

### "Port 20007 bereits belegt"
→ Ein anderes Programm nutzt den Port
→ Anderen Port in config.ini eintragen (z.B. 20008)
→ Im Kassensystem den gleichen Port einstellen

### "COM-Port kann nicht geoeffnet werden"
→ Ist com0com installiert und das Portpaar erstellt?
→ Richtigen Port in config.ini und Kassensystem eingestellt?
→ Wird der Port von einem anderen Programm verwendet?

### Kassensystem meldet "Terminal nicht erreichbar"
→ Gateway laeuft? (start.bat ausfuehren)
→ Richtige IP/Port im Kassensystem eingestellt?
→ Windows Firewall: Port 20007 freigeben

### Zahlung wird nicht am SumUp Solo angezeigt
→ Terminal-ID in config.ini korrekt?
→ SumUp Solo eingeschaltet und mit WLAN verbunden?
→ SumUp Solo mit dem gleichen Konto eingerichtet?

### Logdatei pruefen
Die Datei `zvt2sumup.log` im Programmverzeichnis enthaelt detaillierte Informationen. Bei Problemen hier nachschauen.

---

## FAQ - Haeufige Fragen

### Allgemein

**F: Kostet das Gateway etwas?**
A: Nein, das Gateway selbst ist kostenlos. Es fallen nur die normalen SumUp-Transaktionsgebuehren an.

**F: Brauche ich ein spezielles SumUp-Konto?**
A: Sie benoetigen ein SumUp-Geschaeftskonto mit API-Zugang. Der kostenlose Basis-Account reicht aus.

**F: Funktioniert das auch mit dem SumUp Air oder SumUp 3G?**
A: Prinzipiell ja, solange das Terminal ueber die SumUp API ansteuerbar ist. Getestet wurde es mit dem SumUp Solo.

**F: Muss der PC, auf dem das Gateway laeuft, immer an sein?**
A: Ja. Das Gateway muss laufen, wenn das Kassensystem eine Kartenzahlung ausloesen will. Es reicht aber ein einfacher Windows-PC oder sogar ein Mini-PC.

**F: Kann ich das Gateway als Windows-Dienst starten?**
A: Ja! Siehe den Abschnitt "Als Windows-Dienst betreiben" weiter unten. Der Dienst startet automatisch mit Windows und laeuft im Hintergrund - kein angemeldeter Benutzer noetig.

### Kassensystem

**F: Welche Kassensysteme sind kompatibel?**
A: Jedes Kassensystem, das das ZVT-Protokoll ueber TCP/IP (Port 20007) oder seriell (COM-Port) unterstuetzt. Das sind die meisten deutschen Kassensysteme.

**F: Mein Kassensystem hat nur "EC-Terminal" als Option, kein ZVT.**
A: In den meisten Faellen ist "EC-Terminal" identisch mit ZVT. Probieren Sie die TCP/IP-Verbindung mit Port 20007.

**F: Kann ich mehrere Kassen mit einem Gateway verbinden?**
A: Ja, das TCP-Gateway akzeptiert mehrere gleichzeitige Verbindungen. Allerdings koennen Zahlungen nur nacheinander auf dem Terminal verarbeitet werden.

**F: Mein Kassensystem nutzt ZVT ueber RS-232 (serielle Schnittstelle).**
A: Dann brauchen Sie den COM-Port-Modus und ggf. com0com fuer den virtuellen COM-Port. Siehe Abschnitt "COM-Port-Modus" oben.

### Zahlungen

**F: Wie lange dauert eine Kartenzahlung?**
A: Typischerweise 5-15 Sekunden, je nach Netzwerkgeschwindigkeit und ob kontaktlos oder mit PIN bezahlt wird. Das Gateway wartet bis zu 120 Sekunden (konfigurierbar).

**F: Was passiert bei Netzwerkausfall waehrend der Zahlung?**
A: Das Gateway meldet dem Kassensystem einen Fehler. Es wird KEINE Zahlung durchgefuehrt. Im Zweifelsfall im SumUp Dashboard pruefen.

**F: Funktioniert Storno / Rueckerstattung?**
A: Ja, die letzte Transaktion kann ueber das ZVT-Storno-Kommando zurueckgebucht werden. Fuer aeltere Transaktionen nutzen Sie das SumUp Dashboard.

**F: Werden Belege gedruckt?**
A: Nein, das Gateway unterstuetzt keinen ZVT-Belegdruck. Belege werden digital ueber SumUp erstellt (E-Mail/SMS an den Kunden).

### Sicherheit

**F: Ist die Verbindung sicher?**
A: Ja. Die Kommunikation mit SumUp laeuft ueber HTTPS (verschluesselt). Das ZVT-Gateway selbst laeuft standardmaessig nur auf localhost (127.0.0.1) und ist von aussen nicht erreichbar.

**F: Werden Kartendaten auf meinem PC gespeichert?**
A: Nein. Kartendaten werden ausschliesslich vom SumUp Terminal verarbeitet. Das Gateway sieht keine Kartennummern oder PINs.

**F: Ist das PCI-DSS-konform?**
A: Das Gateway verarbeitet keine Kartendaten und faellt daher nicht in den PCI-DSS-Geltungsbereich. Die Kartendatenverarbeitung erfolgt komplett bei SumUp (zertifizierter Payment Facilitator).

### Technisches

**F: Welche ZVT-Version wird unterstuetzt?**
A: Das Gateway implementiert einen Subset des ZVT-Kassenprotokolls (angelehnt an Version 700). Die gaengigsten Kommandos (Registrierung, Zahlung, Storno, Kassenschnitt) sind abgedeckt.

**F: Kann ich das Logging erhoehen?**
A: Ja, in der config.ini den Wert `log_level` auf `DEBUG` setzen. Dann werden alle ZVT-Nachrichten im Detail protokolliert.

**F: Wo finde ich die Logs?**
A: Im Programmverzeichnis unter `zvt2sumup.log`.

---

## Als Windows-Dienst betreiben

Das Gateway kann als **Windows-Dienst** laufen. Vorteile:
- Startet **automatisch mit Windows** (auch ohne Benutzer-Anmeldung)
- Laeuft unsichtbar im **Hintergrund**
- Wird bei Absturz automatisch neu gestartet (konfigurierbar via services.msc)
- Ideal fuer den **Dauerbetrieb** im Geschaeft

### Dienst installieren

1. **Einmalig einrichten:** Rechtsklick auf **`dienst_install.bat`** → **"Als Administrator ausfuehren"**
   - Das Skript prueft die Konfiguration
   - Installiert den Windows-Dienst
   - Startet ihn sofort

Das war's. Der Dienst laeuft jetzt und startet bei jedem Windows-Neustart automatisch.

### Dienst verwalten

| Aktion                    | Methode                                        |
|---------------------------|------------------------------------------------|
| Status pruefen            | `dienst_status.bat` ausfuehren                 |
| Dienst stoppen            | `dienst_entfernen.bat` als Admin ausfuehren    |
| Dienst neu starten        | services.msc → "ZVT-zu-SumUp Gateway" → Neustart |
| Logs pruefen              | `zvt2sumup.log` oeffnen                        |
| Konfiguration aendern     | `setup.bat`, danach Dienst neu starten         |

### Dienst ueber services.msc verwalten

1. Windows-Taste + R → `services.msc` eingeben → Enter
2. In der Liste **"ZVT-zu-SumUp Gateway"** suchen
3. Rechtsklick → Starten / Stoppen / Neu starten / Eigenschaften

In den **Eigenschaften** koennen Sie auch einstellen:
- **Starttyp:** Automatisch (Standard), Manuell, Deaktiviert
- **Wiederherstellung:** Was bei Absturz passiert (z.B. "Dienst neu starten")

### Dienst entfernen

Rechtsklick auf **`dienst_entfernen.bat`** → **"Als Administrator ausfuehren"**

Das Gateway kann danach weiterhin manuell mit `start.bat` gestartet werden.

### Wann Dienst, wann start.bat?

| Szenario                          | Empfehlung      |
|-----------------------------------|-----------------|
| Dauerbetrieb im Geschaeft         | Dienst          |
| Testen und Einrichten             | start.bat       |
| PC wird nur bei Bedarf gestartet  | Dienst          |
| Fehlersuche / Debugging           | start.bat       |

---

## Updates

Doppelklick auf **`update.bat`** - das Skript:

1. Zeigt die aktuelle Version an
2. Prueft ob ein Update auf GitHub verfuegbar ist
3. Fragt ob aktualisiert werden soll
4. Erstellt ein Backup (config.ini wird **nicht** ueberschrieben)
5. Laedt die neue Version herunter und installiert sie
6. Wenn das Gateway als Dienst laeuft, wird es automatisch neu gestartet

**Update-Methoden:**
- Wenn **git** installiert ist: `git pull` (schnell, nur Aenderungen)
- Ohne git: ZIP-Download von GitHub (kompletter Download)

Die `config.ini` und Logdatei bleiben bei jedem Update erhalten.

---

## Dateiuebersicht

```
zvt2sumup/
├── install.bat            ← Einmal ausfuehren: Installiert alles
├── setup.bat              ← Grafischer Einrichtungsassistent
├── start.bat              ← Gateway starten (interaktiv)
├── stop.bat               ← Gateway beenden (interaktiv)
├── update.bat             ← Auf neue Version pruefen und aktualisieren
├── dienst_install.bat     ← Als Windows-Dienst installieren (Admin!)
├── dienst_entfernen.bat   ← Windows-Dienst entfernen (Admin!)
├── dienst_status.bat      ← Dienst-Status anzeigen
├── config.ini             ← Ihre Einstellungen (nach Setup)
├── version.json           ← Aktuelle Versionsinformation
├── zvt2sumup.log          ← Logdatei (nach erstem Start)
├── requirements.txt       ← Python-Paketliste
├── ANLEITUNG.md           ← Diese Datei
│
└── gateway/               ← Programmcode
    ├── __init__.py
    ├── main.py            ← Hauptprogramm
    ├── win_service.py     ← Windows-Dienst
    ├── updater.py         ← Update-Logik
    ├── zvt_protocol.py    ← ZVT-Protokoll-Implementierung
    ├── sumup_api.py       ← SumUp API-Anbindung
    ├── handler.py         ← Kommando-Verarbeitung
    ├── server.py          ← TCP/COM-Server
    ├── config.py          ← Konfigurationsverwaltung
    └── gui_setup.py       ← Einrichtungsassistent
```

---

## Lizenz und Haftung

Dieses Projekt ist freie Software. Nutzung auf eigene Gefahr.

**Keine Gewaehrleistung.** Der Autor uebernimmt keine Haftung fuer Schaeden, die durch die Nutzung dieser Software entstehen. Dies ist keine offiziell zertifizierte Zahlungsloesung.

Fuer den produktiven Einsatz empfehlen wir, das Gateway ausfuehrlich zu testen, bevor es im Geschaeftsbetrieb eingesetzt wird.
