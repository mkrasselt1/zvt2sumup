# ZVT-zu-SumUp Gateway

Gateway zwischen klassischen **ZVT-Kassensystemen** und dem **SumUp Solo** Cloud-Kartenterminal.

Ermoeglicht es, ein guenstiges SumUp Solo als Kartenterminal an jedes Kassensystem anzubinden, das das deutsche ZVT-Protokoll (Zahlungsverkehrstechnik) unterstuetzt - ohne teure Mietgeraete oder Providervertraege.

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

## Warum?

Viele Kassensysteme in Deutschland kommunizieren mit Kartenterminals ueber das **ZVT-Protokoll** - den deutschen Branchenstandard. Das SumUp Solo unterstuetzt dieses Protokoll nicht, da es ein cloudbasiertes Terminal mit eigener API ist.

Dieses Gateway uebersetzt zwischen beiden Welten:

1. Kassensystem sendet ZVT-Kommando (z.B. "Zahlung 29,90 EUR")
2. Gateway erstellt einen SumUp-Checkout ueber die Cloud-API
3. SumUp Solo zeigt die Zahlung an, Kunde bezahlt
4. Gateway meldet das Ergebnis im ZVT-Format an die Kasse zurueck

## Features

- **ZVT-Protokoll** ueber TCP/IP (Port 20007) oder virtuellen COM-Port
- **Kartenzahlung, Storno, Kassenschnitt, Statusabfrage** und weitere ZVT-Kommandos
- **Automatische Erkennung** von Merchant Code und Terminal-ID
- **Grafischer Einrichtungsassistent** (setup.bat) - nur API-Key eingeben, Rest wird automatisch ermittelt
- **Windows-Dienst** mit automatischem Start - laeuft im Hintergrund ohne angemeldeten Benutzer
- **Auto-Updater** mit Backup und automatischem Dienst-Neustart
- **One-Click-Installation** (install.bat) - installiert Python-Abhaengigkeiten und erstellt Konfiguration
- **Komplett auf Deutsch** dokumentiert (ANLEITUNG.md)

## Schnellstart

### 1. Installation

```
install.bat
```

Installiert Python-Abhaengigkeiten und erstellt die Konfiguration.

### 2. Einrichtung

```
setup.bat
```

Oeffnet den grafischen Assistenten. Sie benoetigen nur Ihren **SumUp API-Schluessel** ([SumUp Developer Portal](https://me.sumup.com/de-de/developer)). Merchant Code und Terminal werden automatisch erkannt.

### 3. Starten

```
start.bat
```

Oder als Windows-Dienst (empfohlen fuer Dauerbetrieb):

```
dienst_install.bat   (als Administrator)
```

### 4. Kassensystem verbinden

Im Kassensystem die ZVT-Einstellungen setzen:

| Einstellung | Wert        |
|-------------|-------------|
| IP-Adresse  | `127.0.0.1` |
| Port        | `20007`     |
| Protokoll   | ZVT (TCP/IP)|

## Voraussetzungen

- **Windows 10/11**
- **Python 3.10+** (wird bei Bedarf von install.bat installiert)
- **Internetverbindung**
- **SumUp-Geschaeftskonto** mit API-Zugang
- **SumUp Solo Terminal**
- **Kassensystem** mit ZVT-Unterstuetzung

## Unterstuetzte ZVT-Kommandos

| Funktion         | ZVT-Kommando | Status       |
|------------------|------------- |--------------|
| Registrierung    | 06 00        | Unterstuetzt |
| Kartenzahlung    | 06 01        | Unterstuetzt |
| Storno           | 06 30        | Unterstuetzt |
| Kassenschnitt    | 06 50        | Unterstuetzt |
| Statusabfrage    | 05 01        | Unterstuetzt |
| Abbruch          | 06 B0        | Unterstuetzt |
| Diagnose         | 06 70        | Unterstuetzt |
| Abmeldung        | 06 02        | Unterstuetzt |

## Einschraenkungen

- **Kein Offline-Betrieb** - benoetigt Internetverbindung
- **Kein vollstaendiger ZVT-Ersatz** - Subset der gaengigsten Kommandos
- **Keine offizielle Zertifizierung** - Community-Projekt
- **Keine Kartendaten auf dem PC** - Kartendatenverarbeitung erfolgt ausschliesslich im SumUp Terminal

## Projektstruktur

```
zvt2sumup/
├── install.bat            One-Click-Installation
├── setup.bat              Grafischer Einrichtungsassistent
├── start.bat              Gateway starten (interaktiv)
├── stop.bat               Gateway beenden
├── update.bat             Auf Updates pruefen
├── dienst_install.bat     Als Windows-Dienst installieren
├── dienst_entfernen.bat   Windows-Dienst entfernen
├── dienst_status.bat      Dienst-Status anzeigen
├── ANLEITUNG.md           Ausfuehrliche deutsche Dokumentation + FAQ
│
└── gateway/
    ├── main.py            Hauptprogramm + GatewayApp-Klasse
    ├── zvt_protocol.py    ZVT-Protokoll (Parser, Builder, TCP+Seriell)
    ├── sumup_api.py       SumUp Cloud-API Client
    ├── handler.py         ZVT-Kommando → SumUp-API Uebersetzung
    ├── server.py          TCP- und COM-Port-Server
    ├── config.py          Konfigurationsverwaltung (config.ini)
    ├── gui_setup.py       Tkinter-Einrichtungsassistent
    ├── win_service.py     Windows-Dienst (pywin32)
    └── updater.py         Git/GitHub-basierter Auto-Updater
```

## Dokumentation

Die vollstaendige Dokumentation auf Deutsch mit Schritt-fuer-Schritt-Anleitung, Fehlerbehebung und FAQ finden Sie in der [ANLEITUNG.md](ANLEITUNG.md).

## Lizenz

Freie Software. Nutzung auf eigene Gefahr. Keine Gewaehrleistung. Dies ist keine offiziell zertifizierte Zahlungsloesung.
