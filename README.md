# DarkMark
# DarkMark 1.1.3

**Ein modernes Tool zur automatischen Schwärzung von PDF-Dokumenten**

DarkMark ist eine benutzerfreundliche Desktop-Anwendung, die entwickelt wurde, um sensible Informationen in PDF-Dokumenten automatisch zu erkennen und zu schwärzen. Mit einer intuitiven grafischen Benutzeroberfläche und leistungsstarker Template-basierter Mustererkennung macht DarkMark den Prozess der Dokumentenschwärzung effizient und zuverlässig.

## 🚀 Hauptfunktionen

- **Template-basierte Erkennung**: Automatische Erkennung von Inhalten basierend auf benutzerdefinierten Bild-Templates
- **Einzeldatei- & Stapelverarbeitung**: Verarbeitung einzelner PDFs oder ganzer Ordner
- **Live-Vorschau**: Sofortige Anzeige der Schwärzungen vor dem Speichern
- **Multi-Threading**: Parallele Verarbeitung für optimale Performance
- **Modernes Dark Theme**: Elegante und augenfreundliche Benutzeroberfläche
- **Sichere Verarbeitung**: Original-Dokumente bleiben unverändert

## 📋 Systemanforderungen

### Python-Version
- Python 3.8 oder höher

### Abhängigkeiten
```
PySide6 >= 6.0.0
qtawesome >= 1.0.0
Pillow >= 8.0.0
numpy >= 1.20.0
opencv-python >= 4.5.0
PyMuPDF >= 1.20.0
```

## 🛠️ Installation

1. **Repository klonen**
   ```bash
   git clone https://github.com/username/darkmark.git
   cd darkmark
   ```

2. **Virtuelle Umgebung erstellen (empfohlen)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # oder
   venv\Scripts\activate     # Windows
   ```

3. **Abhängigkeiten installieren**
   ```bash
   pip install -r requirements.txt
   ```

4. **Template-Ordner vorbereiten**
   - Erstellen Sie einen Ordner namens `darkmark_temp_pages` im Projektverzeichnis
   - Fügen Sie Ihre Template-Bilder (PNG, JPG, JPEG, BMP, TIFF) hinzu

5. **Logo hinzufügen (optional)**
   - Erstellen Sie einen `assets`-Ordner im Projektverzeichnis
   - Fügen Sie eine `logo.png` Datei hinzu (empfohlene Größe: 1024x1024 Pixel)

## 🚀 Verwendung

### Anwendung starten
```bash
python darkmark.py
```

### Grundlegende Arbeitsschritte

1. **Templates vorbereiten**
   - Speichern Sie Bilder der zu erkennenden Inhalte im `darkmark_temp_pages` Ordner
   - Templates sollten repräsentative Ausschnitte der zu schwärzenden Bereiche sein

2. **PDF(s) laden**
   - Klicken Sie auf "Einzelne PDF" für eine Datei
   - Oder wählen Sie "Ganzer Ordner" für Stapelverarbeitung

3. **Vorschau erstellen**
   - Klicken Sie "Vorschau Schwärzung" um zu sehen, was erkannt wird
   - Navigieren Sie durch die Seiten zur Kontrolle

4. **Speichern oder Stapelverarbeitung**
   - "Vorschau speichern" für die aktuelle Datei
   - "Alle PDFs verarbeiten" für den gesamten Ordner

## ⚙️ Konfiguration

### Template-Erkennung anpassen
Im Code können Sie folgende Parameter anpassen:

```python
MATCH_THRESHOLD = 0.6    # Erkennungsgenauigkeit (0.0 - 1.0)
RENDER_DPI = 300         # Auflösung für die Bildverarbeitung
```

### Unterstützte Template-Formate
- PNG
- JPG/JPEG
- BMP
- TIFF

## 🏗️ Projektstruktur

```
darkmark/
├── darkmark.py                 # Hauptanwendung
├── requirements.txt            # Python-Abhängigkeiten
├── darkmark_temp_pages/        # Template-Ordner
│   ├── template1.png
│   └── template2.jpg
├── assets/                     # Ressourcen
│   └── logo.png               # Anwendungslogo
└── README.md                  # Diese Datei
```

## 🔧 Erweiterte Funktionen

### Threading-System
DarkMark nutzt Qt's QThreadPool für parallele Verarbeitung:
- Automatische Thread-Anzahl basierend auf CPU-Kernen
- Non-blocking UI während der Verarbeitung
- Fortschrittsanzeige für Stapelverarbeitung

### Fehlerbehandlung
- Umfassende Fehlerbehandlung für alle Dateivorgänge
- Benutzerfreundliche Fehlermeldungen
- Automatische Aufräumung temporärer Dateien

## 📝 Hinweise zur Verwendung

### Template-Erstellung
- Verwenden Sie klare, hochauflösende Bilder
- Templates sollten typische Beispiele der zu erkennenden Inhalte sein
- Mehrere Templates für verschiedene Variationen desselben Inhalts sind empfehlenswert

### Performance-Optimierung
- Kleinere Templates führen zu schnellerer Verarbeitung
- Die DPI-Einstellung beeinflusst Genauigkeit vs. Geschwindigkeit
- Bei großen Stapelverarbeitungen genügend freien Speicherplatz einplanen

### Datenschutz
- Alle Verarbeitungen erfolgen lokal
- Keine Daten werden über das Internet übertragen
- Original-Dokumente bleiben unverändert

## 🐛 Bekannte Limitierungen

- Templates müssen exakt mit dem zu erkennenden Inhalt übereinstimmen
- Rotierte oder skalierte Inhalte werden möglicherweise nicht erkannt
- Sehr große PDF-Dateien können die Verarbeitung verlangsamen

## 🤝 Beitragen

Beiträge sind willkommen! Bitte:

1. Forken Sie das Repository
2. Erstellen Sie einen Feature-Branch
3. Commiten Sie Ihre Änderungen
4. Pushen Sie zum Branch
5. Öffnen Sie einen Pull Request

## 📄 Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe LICENSE-Datei für Details.

## 👨‍💻 Autor

**Johannes Gschwendtner**

Bei Fragen oder Problemen erstellen Sie bitte ein Issue im GitHub-Repository.

## 🙏 Danksagungen

- PyMuPDF für die PDF-Verarbeitung
- OpenCV für die Bildverarbeitung
- PySide6 für die moderne GUI
- Qt Awesome für die Icons

---

*DarkMark - Sichere und effiziente PDF-Schwärzung für den professionellen Einsatz.*

