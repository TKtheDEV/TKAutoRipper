# TKAutoRipper

**Status:** ALPHA, use for testing purposes only

**Supported platform:** **Ubuntu 25.4 and later**
**Testing platforms** **macOS (arm)** **Windows 11**

TKAutoRipper: Awesome scalable zero click optical media backup solution.  
It detects disc inserts, backs up the data and transcodes/compresses it afterwards.

> ⚠️ **Disclaimer**
>
> - Under active development, not stable, no eta. feel free to reach out if you want to contribute. @legendaryz_fps on discord
> - APIs and config structure will change.
> - You agree to run this piece of software on your own risk. I am not responsible for potential damage to your system nor legal consequences if used for illegal purposes. Check your local laws!

> **Note:**
>
> - Windows code has issues, not all features are supported. What works: DVDs/BLURAYs, What doesn't: GPU metrics, CPU temp, CDs, XX_rom, ejecting the drive (real buggy, usually the 20th eject works)
> - MacOS code has issues, not all features are supported. What works: DVDs/BLURAYs, What doesn't: Multi drive support, GPU metrics, CPU temp, CDs, XX_rom
> - Windows and Mac only have DVD/BLURAY support at the moment, no CD/Data Disc

---

## 1. Requirements

### 1.1 OS

- Ubuntu Linux 25.04

### 1.2 Third-party tools (must be installed **before** the installer runs)

These are **not** installed automatically; you install them from the official sources:

- **HandBrake (Flatpak)**  
  Used for video transcoding.  
  - App ID: `fr.handbrake.ghb` (from Flathub).  
  - Docs / downloads:  
    - HandBrake: <https://handbrake.fr/docs/>  
    - Flatpak / Flathub page: <https://flathub.org/apps/fr.handbrake.ghb>

- **MakeMKV**  
  Used for DVD / Blu-ray title extraction.  
  - Download / install instructions: <https://makemkv.com/download/>

- **LACT**  
  GPU data provider for the dashboaord.  
  - Project page / docs: <https://github.com/ilya-zlobintsev/LACT>  
  - Service usually runs as `lactd` and listens on `/run/lactd.sock`.

The installer will **check** for these and stop with helpful links if something is missing.

### 1.3 System packages (will be installed from Ubuntu repos)

These are installed by the installer script if missing:

- `python3`, `python3-venv`, `python3-pip`
- `abcde`
- `zstd`, `bzip2`
- common base tools that should already be present on Ubuntu: `coreutils`, `util-linux`, `udev`, `eject`

---

## 2. Quick install (Ubuntu)

> **TL;DR:** clone → run installer → start app.

```bash
# 1) Clone the repo
git clone https://github.com/TKtheDEV/TKAutoRipper.git
cd TKAutoRipper

# 2) Run the Ubuntu installer (checks HB Flatpak, MakeMKV, LACT, then sets everything up)
bash installer/linux.sh

# 3) Activate the virtualenv and start TKAutoRipper
source .venv/bin/activate
python3 main.py
```

## 3. Manual install

### Windows:

- Python needs to be installed
- MakeMKV needs to be installed
- HandBrakeCLI needs to be installed

```bash
# 1) Clone the repo
cd /D %HOMEDRIVE%%HOMEPATH%
git clone https://github.com/TKtheDEV/TKAutoRipper.git
cd TKAutoRipper

# 2) Create venv
python -m venv venv

# 3) Activate venv (required every time you want to start the program)
.\venv\Scripts\activate.bat
pip install -r installer/requirements_windows.txt
python main.py
```

### macOS:

- Python needs to be installed
- MakeMKV needs to be installed
- HandBrakeCLI needs to be installed

```bash
# 1) Clone the repo
cd
git clone https://github.com/TKtheDEV/TKAutoRipper.git
cd TKAutoRipper

# 2) Create venv
python3 -m venv venv

# 3) Activate venv (required every time you want to start the program)
source venv/bin/activate
pip install -r installer/requirements_macos.txt
python3 main.py
```
