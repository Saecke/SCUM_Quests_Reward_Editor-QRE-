# SCUM Quest Reward Editor

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

- **Python 3.8+**
- For the Qt build: PySide6 — **installed automatically** on first start.
- For the Tkinter build: `tkinter`, bundled with Python on Windows/macOS.
  On Debian/Ubuntu/Mint install it once with `sudo apt install python3-tk`.

## Run

```bash
python3 reward_editor.py          # Qt build (recommended)
# or
python3 reward_editor_tk.py       # dependency-free Tkinter build
```

### First start (Qt build)

If PySide6 is missing, the script creates a local `.venv` next to itself,
installs PySide6 into it, and relaunches from that venv. This takes 1–2 minutes
once and needs an internet connection. A virtual environment is used on purpose:
it avoids the `externally-managed-environment` error (PEP 668) that a plain
`pip install` triggers on modern Linux.

If the automatic install fails (no internet, or `python3-venv` missing on Linux:
`sudo apt install python3-venv`), just use `reward_editor_tk.py` instead.

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
  **Preview** before **Apply**. The *Exclude skill quests* checkbox protects a
  `Skillmaster` folder from accidental scaling.
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

TODO: add a license (e.g. MIT) before publishing.
