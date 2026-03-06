# Temperatuur Monitor (GUI + EXE + Arduino)

Dit pakket is bedoeld om direct op GitHub te zetten voor anderen.
Het bevat zowel de broncode als een reeds gebouwde Windows executable.

## Inhoud van deze map

- `temp_gui.py`
  - De hoofdapp (PySide6 GUI) die seriele data van de Arduino uitleest, live grafieken toont en CSV-logbestanden wegschrijft.
- `requirements.txt`
  - Alle Python dependencies om de app lokaal te draaien en om een exe te bouwen.
- `Logo.ico`
  - Icoon van de applicatie (venster, taakbalk en exe-icoon bij build).
- `TemperatuurMonitor.exe`
  - Reeds gebouwde Windows executable.
- `arduino/Tempmeter_arduinoV2.ino`
  - Arduino sketch voor de temperatuurmetingen.
- `arduino/Sensor_adres_code.ino`
  - Arduino helper sketch om sensoradressen op te zoeken/controleren.

## Snel starten (alleen EXE gebruiken)

1. Download de map of release.
2. Start `TemperatuurMonitor.exe`.
3. Sluit de Arduino aan via USB.
4. Klik in de app op `Bladeren` en kies een logmap.
5. Gebruik:
   - `Loggen starten` voor sensordata
   - `Omgevingstemperatuur` + `Loggen` voor handmatige omgevingstemp

## CSV logging gedrag

- De eerste logactie maakt een sessiemap aan, bijvoorbeeld:
  - `Temperatuur_meting_2026-03-06_14-25-10`
- In die sessiemap komen:
  - `metingen.csv` (sensor1-4)
  - `omgevingstemperatuur.csv` (handmatige omgevingstemp)
- Na `Loggen stoppen` en een nieuwe logactie wordt een nieuwe sessiemap gemaakt.

## Zelf draaien met Python (zonder EXE)

### Vereisten

- Windows
- Python 3.10 of hoger (3.11 aanbevolen)

### Installatie

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Starten

```powershell
python temp_gui.py
```

## Zelf een EXE bouwen met PyInstaller

Voer dit uit in dezelfde map als `temp_gui.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pyinstaller --noconfirm --clean --onefile --windowed --name TemperatuurMonitor --icon Logo.ico --add-data "Logo.ico;." temp_gui.py
```

Resultaat:

- `dist\TemperatuurMonitor.exe`

## Arduino seriele output

De GUI verwacht regels in dit formaat:

```text
T,<sensor1>,<sensor2>,<sensor3>,<sensor4>
```

Voorbeeld:

```text
T,21.34,21.40,21.28,21.31
```

## Veelvoorkomende problemen

- Arduino niet gevonden:
  - Controleer USB-kabel, COM-poort en of de sketch draait.
- COM-poort bezet:
  - Sluit andere seriele tools (bijv. Arduino Serial Monitor).
- EXE wordt geblokkeerd:
  - Windows SmartScreen kan waarschuwen bij ongesigneerde apps.
- Geen data in grafieken:
  - Controleer of de seriele output exact het verwachte formaat heeft.

