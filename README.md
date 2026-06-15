# SCUM Quest Reward Editor

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A small desktop GUI to view and bulk-edit the **rewards** of custom SCUM
quests (the `.json` files in your server's quest `Override` folder).

Edit single quests, or scale **money / gold / fame / skill-XP** across whole
groups linearly (e.g. "all Tier-2 Armorer rewards ×1.5"). Every save writes a
timestamped backup of the originals first, so you can't lose data.

Two interchangeable builds are included:

| File | Toolkit | When to use |
|------|---------|-------------|
| `reward_editor.py` | **PySide6 / Qt** | Recommended. Native look, great dark-theme support. Installs itself (see below). |
| `reward_editor_tk.py` | **Tkinter** | Dependency-free fallback. Ships with the standard Python installer on Windows/macOS. |

---

## Requirements

Only **Python 3.8+** is required. Everything else is handled per build:

- **Qt build** (`reward_editor.py`) — installs PySide6 automatically on first start.
- **Tkinter build** (`reward_editor_tk.py`) — no extra packages on Windows/macOS;
  on Linux you may need the system `tkinter` package (see below).

## Install & Run

The tool runs on **Windows, Linux and macOS**. Pick your OS:

### 🪟 Windows

1. Install Python from [python.org](https://www.python.org/downloads/) and tick
   **"Add python.exe to PATH"** in the installer. (Tkinter is included.)
2. Download/clone this folder, then **double-click `reward_editor.py`** — or open
   a terminal in the folder and run:
   ```bat
   python reward_editor.py          REM Qt build (recommended)
   python reward_editor_tk.py       REM no-dependency Tkinter build
   ```
   Tip: to start without a console window, use `pythonw reward_editor.py`.

### 🐧 Linux

```bash
python3 reward_editor.py          # Qt build (recommended)
python3 reward_editor_tk.py       # no-dependency Tkinter build
```
For the Qt build's auto-installer you may need `python3-venv`, and for the
Tkinter build `python3-tk` (Debian/Ubuntu/Mint):
```bash
sudo apt install python3-venv python3-tk
```

### 🍎 macOS

Install Python from [python.org](https://www.python.org/downloads/) (includes
Tkinter), then in Terminal:
```bash
python3 reward_editor.py
```

### First start of the Qt build

If PySide6 isn't installed, the script creates a local `.venv` next to itself,
installs PySide6 into it, and relaunches from that venv. This takes 1–2 minutes
once and needs an internet connection. A virtual environment is used on purpose:
it avoids the `externally-managed-environment` error (PEP 668) that a plain
`pip install` triggers on modern Linux.

If the automatic install fails (no internet, or `python3-venv` missing on Linux),
just run `reward_editor_tk.py` instead — it needs no installation.

## Finding your quests

On startup the tool looks for an `Override` folder containing quest `.json`
files, in this order:

1. the `SCUM_QUESTS_DIR` environment variable,
2. a remembered path from a previous run (`.reward_editor_path`),
3. the script's own folder and several parent folders.

If none is found, a folder picker opens — choose your `Override` folder (or the
folder that contains it). Your choice is remembered for next time.

## Usage

- **Filter** by folder / NPC / tier, or search by title and task text.
- **Sort** by clicking any column header.
- **Edit one quest:** click a row, change Money / Gold / Fame / per-skill XP,
  then **Apply (in memory)**.
- **Bulk edit:** pick fields (Money/Gold/Fame/XP), set `new = old × factor + offset`,
  optionally round to a step. Scope is *filtered only* or *ALL quests*. Use
  **Preview** before **Apply**. Tip: set the filters first and use *filtered only*
  to limit scaling to exactly the quests you want.
- **Save:** changes stay in memory (changed rows are highlighted) until you press
  **Save ALL**, which writes the files and drops a `Reward_Backup_<timestamp>/`
  next to your `Override` folder containing the untouched originals.

## Notes

- Edits only touch reward fields (`CurrencyNormal`, `CurrencyGold`, `Fame`,
  `Skills[].Experience`). Quest tasks, items and conditions are left untouched.
- Files are read and written as UTF-8, so German umlauts etc. survive on Windows.
- Negative reward values are shown in red. Per SCUM's official docs `CurrencyGold`
  is what a player *receives*; negative values are an undocumented trick — use with
  care.

## Repository layout

```
reward_editor/
├── reward_editor.py        # Qt build (self-installing)
├── reward_editor_tk.py     # Tkinter build (no dependencies)
├── README.md
└── .gitignore
```

The `Override` folder with the quests is **not** part of this tool — point the
tool at your own. Do **not** commit the generated `.venv/`, `.reward_editor_path`
or `Reward_Backup_*/` folders (see `.gitignore`).

## License

Released under the [MIT License](LICENSE) — free to use, modify and share.
