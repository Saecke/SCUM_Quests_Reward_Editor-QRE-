#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCUM Quest Reward Editor (PySide6 / Qt)
=======================================
Run:   python3 reward_editor.py

Loads every quest from your SCUM quest "Override" folder, shows task + reward,
and lets you edit single rewards or scale whole groups linearly up/down.
Saving always writes a timestamped backup of the originals first.

PySide6 is installed automatically into a local .venv on first start
(no manual pip needed). A dependency-free Tkinter build sits next to this
file as reward_editor_tk.py in case Qt is unavailable.
"""

import os, sys, glob, json, shutil, datetime, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))


# ============================================================ Auto-setup PySide6
def _ensure_pyside6():
    """Make sure PySide6 is importable. If not, create a local .venv, install
    PySide6 into it and re-launch the script from that venv. Using a venv avoids
    the 'externally-managed-environment' error (PEP 668) on modern Linux."""
    try:
        import PySide6  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get("REWARD_EDITOR_BOOTSTRAPPED"):
        sys.stderr.write(
            "\nPySide6 could not be provisioned automatically.\n"
            "Manual fix:  pip install pyside6\n"
            "Or use the dependency-free reward_editor_tk.py\n")
        sys.exit(1)

    venv_dir = os.path.join(BASE, ".venv")
    is_win = os.name == "nt"
    vpy = os.path.join(venv_dir, "Scripts" if is_win else "bin",
                       "python.exe" if is_win else "python")
    try:
        if not os.path.exists(vpy):
            print("First run: creating a local environment (.venv) and installing "
                  "PySide6 - this takes 1-2 minutes once...", flush=True)
            import venv
            venv.create(venv_dir, with_pip=True)
        subprocess.run([vpy, "-m", "pip", "install", "--upgrade", "pip"],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([vpy, "-m", "pip", "install", "pyside6"], check=True)
    except Exception as e:
        sys.stderr.write(
            f"\nAutomatic installation failed: {e}\n"
            "Likely causes: no internet connection, or on Linux the 'python3-venv'\n"
            "package is missing (once:  sudo apt install python3-venv).\n"
            "Install-free alternative: run reward_editor_tk.py instead.\n")
        sys.exit(1)

    env = dict(os.environ, REWARD_EDITOR_BOOTSTRAPPED="1")
    script = os.path.abspath(__file__)
    if is_win:
        sys.exit(subprocess.run([vpy, script, *sys.argv[1:]], env=env).returncode)
    else:
        os.execve(vpy, [vpy, script, *sys.argv[1:]], env)


_ensure_pyside6()

# Set once the Override folder is located (see locate_override / main).
OVERRIDE = None
CONFIG = os.path.join(BASE, ".reward_editor_path")


# ============================================================ Data model (Qt-free)
class Quest:
    def __init__(self, path, data):
        self.path = path
        self.data = data
        rel = os.path.relpath(path, OVERRIDE)
        parts = rel.split(os.sep)
        self.folder = parts[0] if len(parts) > 1 else "(root)"
        self.dirty = False

    @property
    def title(self):  return self.data.get("Title") or os.path.basename(self.path)
    @property
    def npc(self):    return self.data.get("AssociatedNpc", "?")
    @property
    def tier(self):   return self.data.get("Tier", "?")
    @property
    def pools(self):  return self.data.get("RewardPool", []) or []

    def _sum(self, key): return sum((p.get(key) or 0) for p in self.pools)
    @property
    def money(self): return self._sum("CurrencyNormal")
    @property
    def gold(self):  return self._sum("CurrencyGold")
    @property
    def fame(self):  return self._sum("Fame")
    @property
    def xp(self):
        return sum((s.get("Experience") or 0) for p in self.pools for s in p.get("Skills", []))
    @property
    def items(self):
        return [(d.get("Item"), d.get("Amount", 1), d.get("Price", 0))
                for p in self.pools for d in p.get("TradeDeals", [])]

    def task(self):
        parts = []
        for c in sorted(self.data.get("Conditions", []), key=lambda x: x.get("SequenceIndex", 0)):
            t = c.get("Type", "?")
            items = []
            for ri in c.get("RequiredItems", []):
                acc = "/".join(ri.get("AcceptedItems", []))
                n = ri.get("RequiredNum", "")
                qual = ri.get("MinAcceptedCookQuality")
                items.append(f"{n}x {acc}" + (f" ({qual})" if qual else ""))
            if items:                parts.append(f"{t}: " + ", ".join(items))
            elif t == "Interaction": parts.append(f"Interact x{c.get('MaxNeeded', 1)}")
            else:                    parts.append(t)
        return "  +  ".join(parts) or "-"

    def reward_str(self):
        r = []
        if self.money: r.append(f"{self.money}$")
        if self.gold:  r.append(f"{self.gold}G")
        if self.fame:  r.append(f"{self.fame} Fame")
        for p in self.pools:
            for s in p.get("Skills", []):
                r.append(f"+{s.get('Experience')}xp {s.get('Skill')}")
        for it, amt, pr in self.items:
            r.append(f"[Item {amt}x {it}{'@'+str(pr)+'$' if pr else ' free'}]")
        return ", ".join(r) or "-"

    def scale(self, fields, factor, offset, round_to):
        def apply(v):
            v = v * factor + offset
            if round_to and round_to > 1:
                v = round(v / round_to) * round_to
            return int(round(v))
        changed = False
        for p in self.pools:
            for key, flag in (("CurrencyNormal", "money"), ("CurrencyGold", "gold"), ("Fame", "fame")):
                if flag in fields and p.get(key) is not None:
                    nv = apply(p[key])
                    if nv != p[key]: p[key] = nv; changed = True
            if "xp" in fields:
                for s in p.get("Skills", []):
                    if s.get("Experience") is not None:
                        nv = apply(s["Experience"])
                        if nv != s["Experience"]: s["Experience"] = nv; changed = True
        if changed: self.dirty = True
        return changed

    def preview_value(self, base, factor, offset, round_to):
        v = base * factor + offset
        if round_to and round_to > 1:
            v = round(v / round_to) * round_to
        return int(round(v))

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        self.dirty = False


def load_quests():
    out = []
    for p in sorted(glob.glob(os.path.join(OVERRIDE, "**", "*.json"), recursive=True)):
        try:
            out.append(Quest(p, json.load(open(p, encoding="utf-8"))))
        except Exception as e:
            print(f"Parse error {p}: {e}", file=sys.stderr)
    return out


# ============================================================ Override discovery
def _has_json(d):
    return bool(glob.glob(os.path.join(d, "**", "*.json"), recursive=True))


def locate_override():
    """Find the quest 'Override' folder without asking. Returns a path or None.
    Order: env var, remembered path, then script dir + several parent levels."""
    candidates = []
    if os.environ.get("SCUM_QUESTS_DIR"):
        candidates.append(os.environ["SCUM_QUESTS_DIR"])
    if os.path.isfile(CONFIG):
        try:
            candidates.append(open(CONFIG, encoding="utf-8").read().strip())
        except OSError:
            pass
    d = BASE
    for _ in range(6):
        candidates.append(os.path.join(d, "Override"))
        d = os.path.dirname(d)
    for c in candidates:
        if c and os.path.isdir(c) and _has_json(c):
            return c
    return None


def normalize_override(chosen):
    """Accept either the 'Override' folder itself or a parent that contains it."""
    if not chosen:
        return None
    sub = os.path.join(chosen, "Override")
    if os.path.isdir(sub) and _has_json(sub):
        return sub
    if _has_json(chosen):
        return chosen
    return None


def remember_override(path):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            f.write(path)
    except OSError:
        pass


# ============================================================ GUI
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QGroupBox,
    QPushButton, QCheckBox, QRadioButton, QButtonGroup, QMessageBox, QHeaderView,
    QAbstractItemView, QFileDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush

NUMERIC = {"money", "gold", "fame", "xp"}


class NumItem(QTableWidgetItem):
    """Table cell that sorts numerically instead of alphabetically."""
    def __init__(self, value):
        super().__init__(str(value))
        self._v = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setFlags(self.flags() & ~Qt.ItemFlag.ItemIsEditable)
    def __lt__(self, other):
        try: return self._v < other._v
        except AttributeError: return super().__lt__(other)


class App(QMainWindow):
    COLS = [("folder", "Folder"), ("npc", "NPC"), ("tier", "T"), ("title", "Quest"),
            ("money", "Money"), ("gold", "Gold"), ("fame", "Fame"), ("xp", "XP"),
            ("items", "Items"), ("dirty", "*")]

    def __init__(self, quests):
        super().__init__()
        self.quests = quests
        self.setWindowTitle("SCUM Quest Reward Editor")
        self.resize(1200, 760)
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.addWidget(self._filters())
        root.addWidget(self._table(), stretch=1)
        root.addWidget(self._editor())
        root.addWidget(self._bulk())
        root.addLayout(self._footer())
        self._cur = None
        self.refresh()

    # ---------- filters ----------
    def _filters(self):
        box = QGroupBox("Filter"); h = QHBoxLayout(box)
        self.cb_folder = QComboBox(); self.cb_npc = QComboBox(); self.cb_tier = QComboBox()
        self.cb_folder.addItems(["(all)"] + sorted({q.folder for q in self.quests}))
        self.cb_npc.addItems(["(all)"] + sorted({q.npc for q in self.quests}))
        self.cb_tier.addItems(["(all)"] + sorted({str(q.tier) for q in self.quests}))
        for lbl, cb in (("Folder", self.cb_folder), ("NPC", self.cb_npc), ("Tier", self.cb_tier)):
            h.addWidget(QLabel(lbl)); h.addWidget(cb)
            cb.currentIndexChanged.connect(self.refresh)
        h.addSpacing(12); h.addWidget(QLabel("Search"))
        self.ed_search = QLineEdit(); self.ed_search.setMaximumWidth(220)
        self.ed_search.textChanged.connect(self.refresh)
        h.addWidget(self.ed_search); h.addStretch(1)
        self.lbl_count = QLabel(""); h.addWidget(self.lbl_count)
        return box

    # ---------- table ----------
    def _table(self):
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([c[1] for c in self.COLS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.on_select)
        return self.table

    # ---------- single-quest editor ----------
    def _editor(self):
        box = QGroupBox("Edit selected quest"); g = QGridLayout(box)
        self.lbl_info = QLabel("(no selection)")
        f = self.lbl_info.font(); f.setBold(True); self.lbl_info.setFont(f)
        g.addWidget(self.lbl_info, 0, 0, 1, 8)
        self.lbl_task = QLabel(""); self.lbl_task.setStyleSheet("color:#888")
        self.lbl_task.setWordWrap(True)
        g.addWidget(self.lbl_task, 1, 0, 1, 8)
        self.e_money = QLineEdit(); self.e_gold = QLineEdit(); self.e_fame = QLineEdit()
        for i, (lbl, w) in enumerate((("Money", self.e_money), ("Gold", self.e_gold), ("Fame", self.e_fame))):
            w.setMaximumWidth(90)
            g.addWidget(QLabel(lbl), 2, i * 2, Qt.AlignmentFlag.AlignRight); g.addWidget(w, 2, i * 2 + 1)
        self.skill_box = QWidget(); self.skill_layout = QHBoxLayout(self.skill_box)
        self.skill_layout.setContentsMargins(0, 0, 0, 0)
        g.addWidget(self.skill_box, 3, 0, 1, 8)
        self.skill_edits = []
        btn = QPushButton("Apply (in memory)"); btn.clicked.connect(self.apply_single)
        g.addWidget(btn, 2, 6, 1, 2)
        return box

    # ---------- bulk ----------
    def _bulk(self):
        box = QGroupBox("Bulk edit (linear scale)"); g = QGridLayout(box)
        self.rb_filter = QRadioButton("filtered only"); self.rb_all = QRadioButton("ALL quests")
        self.rb_filter.setChecked(True)
        grp = QButtonGroup(self); grp.addButton(self.rb_filter); grp.addButton(self.rb_all)
        g.addWidget(self.rb_filter, 0, 0); g.addWidget(self.rb_all, 0, 1)
        self.bf = {}
        for i, (k, lbl) in enumerate((("money", "Money"), ("gold", "Gold"), ("fame", "Fame"), ("xp", "XP"))):
            cb = QCheckBox(lbl); cb.setChecked(k == "money"); self.bf[k] = cb
            g.addWidget(cb, 0, 2 + i)
        self.cb_skip = QCheckBox("Exclude skill quests (Skillmaster folder)"); self.cb_skip.setChecked(True)
        g.addWidget(self.cb_skip, 0, 7)
        self.e_factor = QLineEdit("1.0"); self.e_offset = QLineEdit("0"); self.e_round = QLineEdit("0")
        for w in (self.e_factor, self.e_offset, self.e_round): w.setMaximumWidth(80)
        g.addWidget(QLabel("x factor"), 1, 0, Qt.AlignmentFlag.AlignRight); g.addWidget(self.e_factor, 1, 1)
        g.addWidget(QLabel("+ offset"), 1, 2, Qt.AlignmentFlag.AlignRight); g.addWidget(self.e_offset, 1, 3)
        g.addWidget(QLabel("round to"), 1, 4, Qt.AlignmentFlag.AlignRight); g.addWidget(self.e_round, 1, 5)
        b1 = QPushButton("Preview"); b1.clicked.connect(lambda: self.apply_bulk(True))
        b2 = QPushButton("Apply"); b2.clicked.connect(lambda: self.apply_bulk(False))
        g.addWidget(b1, 1, 6); g.addWidget(b2, 1, 7)
        g.addWidget(QLabel("new = old x factor + offset, then round"), 2, 0, 1, 8)
        return box

    # ---------- footer ----------
    def _footer(self):
        h = QHBoxLayout()
        self.lbl_status = QLabel(""); h.addWidget(self.lbl_status); h.addStretch(1)
        b_reload = QPushButton("Reload (discard changes)"); b_reload.clicked.connect(self.reload)
        b_save = QPushButton("Save ALL (with backup)"); b_save.clicked.connect(self.save_all)
        b_save.setStyleSheet("font-weight:bold")
        h.addWidget(b_reload); h.addWidget(b_save)
        return h

    # ---------- logic ----------
    def filtered(self):
        out = []
        s = self.ed_search.text().strip().lower()
        for q in self.quests:
            if self.cb_folder.currentText() != "(all)" and q.folder != self.cb_folder.currentText(): continue
            if self.cb_npc.currentText() != "(all)" and q.npc != self.cb_npc.currentText(): continue
            if self.cb_tier.currentText() != "(all)" and str(q.tier) != self.cb_tier.currentText(): continue
            if s and s not in q.title.lower() and s not in q.task().lower(): continue
            out.append(q)
        return out

    def refresh(self):
        rows = self.filtered()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        dirty_bg = QBrush(QColor("#ffe08a")); neg_fg = QBrush(QColor("#b02a37"))
        dirty_fg = QBrush(QColor("#1a1a1a"))
        for r, q in enumerate(rows):
            vals = {"folder": q.folder, "npc": q.npc, "tier": q.tier, "title": q.title,
                    "money": q.money, "gold": q.gold, "fame": q.fame, "xp": q.xp,
                    "items": len(q.items), "dirty": "*" if q.dirty else ""}
            neg = (q.money < 0 or q.gold < 0 or q.fame < 0)
            for c, (key, _) in enumerate(self.COLS):
                if key in NUMERIC or key == "items":
                    it = NumItem(vals[key])
                else:
                    it = QTableWidgetItem(str(vals[key]))
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, q.path)
                if q.dirty:
                    it.setBackground(dirty_bg); it.setForeground(dirty_fg)
                if neg and key in ("money", "gold", "fame"):
                    it.setForeground(neg_fg)
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        for c in range(len(self.COLS)):
            if c != 3: self.table.resizeColumnToContents(c)
        ndirty = sum(1 for q in self.quests if q.dirty)
        self.lbl_count.setText(f"{len(rows)} shown / {len(self.quests)} total")
        self.lbl_status.setText(f"{ndirty} unsaved change(s)")

    def _selected_quest(self):
        items = self.table.selectedItems()
        if not items: return None
        path = self.table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((q for q in self.quests if q.path == path), None)

    def on_select(self):
        q = self._selected_quest(); self._cur = q
        if not q: return
        self.lbl_info.setText(f"[{q.npc} T{q.tier}] {q.title}")
        self.lbl_task.setText("Task: " + q.task())
        self.e_money.setText(str(q.money)); self.e_gold.setText(str(q.gold)); self.e_fame.setText(str(q.fame))
        while self.skill_layout.count():
            w = self.skill_layout.takeAt(0).widget()
            if w: w.deleteLater()
        self.skill_edits = []
        for p in q.pools:
            for s in p.get("Skills", []):
                self.skill_layout.addWidget(QLabel(f"XP {s.get('Skill')}"))
                e = QLineEdit(str(s.get("Experience", 0))); e.setMaximumWidth(90)
                self.skill_layout.addWidget(e); self.skill_edits.append((s, e))
        self.skill_layout.addStretch(1)

    def apply_single(self):
        q = self._cur
        if not q: return
        try:
            money = int(float(self.e_money.text())); gold = int(float(self.e_gold.text()))
            fame = int(float(self.e_fame.text()))
            skills = [(s, int(float(e.text()))) for s, e in self.skill_edits]
        except ValueError:
            QMessageBox.critical(self, "Error", "Please enter numbers only."); return
        if q.pools:
            p = q.pools[0]
            if "CurrencyNormal" in p or money: p["CurrencyNormal"] = money
            if "CurrencyGold" in p or gold:    p["CurrencyGold"] = gold
            if "Fame" in p or fame:            p["Fame"] = fame
        for s, val in skills: s["Experience"] = val
        q.dirty = True
        self.refresh()
        self.lbl_status.setText(f"'{q.title}' updated (not saved yet).")

    def _bulk_targets(self):
        rows = self.quests if self.rb_all.isChecked() else self.filtered()
        if self.cb_skip.isChecked():
            rows = [q for q in rows if q.folder != "Skillmaster"]
        return rows

    def _bulk_params(self):
        fields = {k for k, cb in self.bf.items() if cb.isChecked()}
        factor = float(self.e_factor.text()); offset = float(self.e_offset.text())
        round_to = int(float(self.e_round.text()))
        return fields, factor, offset, round_to

    def apply_bulk(self, preview):
        try:
            fields, factor, offset, round_to = self._bulk_params()
        except ValueError:
            QMessageBox.critical(self, "Error", "Factor / offset / round must be numbers."); return
        if not fields:
            QMessageBox.warning(self, "Note", "No field selected."); return
        targets = self._bulk_targets()
        formula = f"old x {factor} + {offset}" + (f", rounded to {round_to}" if round_to > 1 else "")
        if preview:
            lines = []
            for q in targets[:14]:
                ch = []
                if "money" in fields and q.money: ch.append(f"{q.money}->{q.preview_value(q.money, factor, offset, round_to)}$")
                if "fame" in fields and q.fame:  ch.append(f"{q.fame}->{q.preview_value(q.fame, factor, offset, round_to)}F")
                if "gold" in fields and q.gold:  ch.append(f"{q.gold}->{q.preview_value(q.gold, factor, offset, round_to)}G")
                if "xp" in fields and q.xp:      ch.append(f"{q.xp}->{q.preview_value(q.xp, factor, offset, round_to)}xp")
                if ch: lines.append(f"- {q.title[:32]}: " + ", ".join(ch))
            QMessageBox.information(self, f"Preview - {len(targets)} quests affected",
                f"Fields: {', '.join(sorted(fields))}\nFormula: {formula}\n\n"
                + ("\n".join(lines) if lines else "(no values in range)")
                + ("\n..." if len(targets) > 14 else ""))
            return
        if QMessageBox.question(self, "Apply?",
                f"{len(targets)} quests, fields {sorted(fields)}\n{formula}\n\n"
                "Changes memory only - save later via 'Save ALL'."
                ) != QMessageBox.StandardButton.Yes:
            return
        n = sum(1 for q in targets if q.scale(fields, factor, offset, round_to))
        self.refresh()
        self.lbl_status.setText(f"Bulk change applied to {n} quests (unsaved).")

    def save_all(self):
        dirty = [q for q in self.quests if q.dirty]
        if not dirty:
            QMessageBox.information(self, "Nothing to do", "No changes."); return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bdir = os.path.abspath(os.path.join(OVERRIDE, os.pardir, f"Reward_Backup_{stamp}"))
        for q in dirty:
            dst = os.path.join(bdir, os.path.relpath(q.path, OVERRIDE))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(q.path, dst); q.save()
        self.refresh()
        QMessageBox.information(self, "Saved",
            f"{len(dirty)} file(s) saved.\nBackup of the originals:\n{bdir}")

    def reload(self):
        if any(q.dirty for q in self.quests) and QMessageBox.question(
                self, "Reload", "Discard unsaved changes?"
                ) != QMessageBox.StandardButton.Yes:
            return
        self.quests = load_quests(); self.refresh()
        self.lbl_status.setText("Reloaded.")


def main():
    global OVERRIDE
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    OVERRIDE = locate_override()
    while not OVERRIDE:
        QMessageBox.information(None, "Select quest folder",
            "Could not find your SCUM quest 'Override' folder automatically.\n\n"
            "Please pick it (or the folder that contains it) in the next dialog.")
        chosen = QFileDialog.getExistingDirectory(None, "Select your SCUM quest 'Override' folder")
        if not chosen:
            return  # user cancelled
        OVERRIDE = normalize_override(chosen)
        if not OVERRIDE:
            QMessageBox.warning(None, "No quests found",
                "That folder contains no quest .json files. Try again.")
    remember_override(OVERRIDE)

    App(load_quests()).show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
