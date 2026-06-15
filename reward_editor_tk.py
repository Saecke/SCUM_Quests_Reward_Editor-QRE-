#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCUM Quest Reward Editor (Tkinter, dependency-free)
===================================================
Run:   python3 reward_editor_tk.py

Same tool as reward_editor.py but built on Tkinter, which ships with the
standard Python installer on Windows/macOS (on Debian/Ubuntu/Mint you may need
'sudo apt install python3-tk'). Use this build when PySide6/Qt is unavailable.

Loads every quest from your SCUM quest "Override" folder, shows task + reward,
and lets you edit single rewards or scale whole groups linearly up/down.
Saving always writes a timestamped backup of the originals first.
"""

import os, sys, glob, json, shutil, datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE = os.path.dirname(os.path.abspath(__file__))
OVERRIDE = None
CONFIG = os.path.join(BASE, ".reward_editor_path")


# ============================================================ Data model
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
class App(tk.Tk):
    COLS = [("folder", "Folder", 110), ("npc", "NPC", 95), ("tier", "T", 30),
            ("title", "Quest", 280), ("money", "Money", 70), ("gold", "Gold", 55),
            ("fame", "Fame", 70), ("xp", "XP", 80), ("items", "Items", 50),
            ("dirty", "*", 24)]

    def __init__(self, quests):
        super().__init__()
        self.title("SCUM Quest Reward Editor")
        self.geometry("1180x720")
        self.quests = quests
        self._sort = (None, False)
        self._build_filters()
        self._build_table()
        self._build_editor()
        self._build_bulk()
        self._build_bottom()
        self.refresh()

    def _build_filters(self):
        f = ttk.LabelFrame(self, text="Filter"); f.pack(fill="x", padx=8, pady=(8, 4))
        self.f_folder = tk.StringVar(value="(all)")
        self.f_npc = tk.StringVar(value="(all)")
        self.f_tier = tk.StringVar(value="(all)")
        self.f_search = tk.StringVar()
        folders = ["(all)"] + sorted({q.folder for q in self.quests})
        npcs = ["(all)"] + sorted({q.npc for q in self.quests})
        tiers = ["(all)"] + sorted({str(q.tier) for q in self.quests})
        for lbl, var, vals in [("Folder", self.f_folder, folders),
                               ("NPC", self.f_npc, npcs), ("Tier", self.f_tier, tiers)]:
            ttk.Label(f, text=lbl).pack(side="left", padx=(8, 2))
            cb = ttk.Combobox(f, textvariable=var, values=vals, width=14, state="readonly")
            cb.pack(side="left"); cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Label(f, text="Search").pack(side="left", padx=(12, 2))
        e = ttk.Entry(f, textvariable=self.f_search, width=22); e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self.refresh())
        self.lbl_count = ttk.Label(f, text=""); self.lbl_count.pack(side="right", padx=8)

    def _build_table(self):
        wrap = ttk.Frame(self); wrap.pack(fill="both", expand=True, padx=8)
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="headings")
        for key, head, w in self.COLS:
            self.tree.heading(key, text=head, command=lambda k=key: self.sort_by(k))
            anchor = "e" if key in ("money", "gold", "fame", "xp") else "w"
            self.tree.column(key, width=w, anchor=anchor, stretch=(key == "title"))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.tag_configure("dirty", background="#ffe08a", foreground="#1a1a1a")
        self.tree.tag_configure("neg", foreground="#b02a37")

    def _build_editor(self):
        self.ed = ttk.LabelFrame(self, text="Edit selected quest")
        self.ed.pack(fill="x", padx=8, pady=4)
        self.ed_info = ttk.Label(self.ed, text="(no selection)", font=("", 10, "bold"))
        self.ed_info.grid(row=0, column=0, columnspan=8, sticky="w", padx=6, pady=(4, 0))
        self.ed_task = ttk.Label(self.ed, text="", foreground="#777")
        self.ed_task.grid(row=1, column=0, columnspan=8, sticky="w", padx=6)
        self.ev = {k: tk.StringVar() for k in ("money", "gold", "fame")}
        for i, (lbl, key) in enumerate([("Money", "money"), ("Gold", "gold"), ("Fame", "fame")]):
            ttk.Label(self.ed, text=lbl).grid(row=2, column=i * 2, sticky="e", padx=(8, 2), pady=6)
            ttk.Entry(self.ed, textvariable=self.ev[key], width=10).grid(row=2, column=i * 2 + 1, sticky="w")
        self.skill_frame = ttk.Frame(self.ed)
        self.skill_frame.grid(row=3, column=0, columnspan=8, sticky="w", padx=6)
        self.skill_vars = []
        ttk.Button(self.ed, text="Apply (in memory)", command=self.apply_single)\
            .grid(row=2, column=6, columnspan=2, padx=8)
        self._cur = None

    def _build_bulk(self):
        b = ttk.LabelFrame(self, text="Bulk edit (linear scale)")
        b.pack(fill="x", padx=8, pady=4)
        self.bulk_scope = tk.StringVar(value="filter")
        ttk.Radiobutton(b, text="filtered only", variable=self.bulk_scope, value="filter").grid(row=0, column=0, padx=6)
        ttk.Radiobutton(b, text="ALL quests", variable=self.bulk_scope, value="all").grid(row=0, column=1)
        self.bf = {k: tk.BooleanVar(value=(k == "money")) for k in ("money", "gold", "fame", "xp")}
        for i, (k, lbl) in enumerate([("money", "Money"), ("gold", "Gold"), ("fame", "Fame"), ("xp", "XP")]):
            ttk.Checkbutton(b, text=lbl, variable=self.bf[k]).grid(row=0, column=2 + i, padx=4)
        self.b_factor = tk.StringVar(value="1.0")
        self.b_offset = tk.StringVar(value="0")
        self.b_round = tk.StringVar(value="0")
        ttk.Label(b, text="x factor").grid(row=1, column=0, sticky="e", padx=4, pady=6)
        ttk.Entry(b, textvariable=self.b_factor, width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(b, text="+ offset").grid(row=1, column=2, sticky="e")
        ttk.Entry(b, textvariable=self.b_offset, width=8).grid(row=1, column=3, sticky="w")
        ttk.Label(b, text="round to").grid(row=1, column=4, sticky="e")
        ttk.Entry(b, textvariable=self.b_round, width=8).grid(row=1, column=5, sticky="w")
        ttk.Button(b, text="Preview", command=lambda: self.apply_bulk(preview=True)).grid(row=1, column=6, padx=4)
        ttk.Button(b, text="Apply", command=lambda: self.apply_bulk(preview=False)).grid(row=1, column=7, padx=4)
        ttk.Label(b, text="new = old x factor + offset, then round").grid(row=2, column=0, columnspan=8, sticky="w", padx=6)

    def _build_bottom(self):
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8, pady=(4, 8))
        self.status = ttk.Label(bar, text=""); self.status.pack(side="left")
        ttk.Button(bar, text="Reload (discard changes)", command=self.reload).pack(side="right", padx=4)
        ttk.Button(bar, text="Save ALL (with backup)", command=self.save_all).pack(side="right", padx=4)

    def filtered(self):
        out = []
        for q in self.quests:
            if self.f_folder.get() != "(all)" and q.folder != self.f_folder.get(): continue
            if self.f_npc.get() != "(all)" and q.npc != self.f_npc.get(): continue
            if self.f_tier.get() != "(all)" and str(q.tier) != self.f_tier.get(): continue
            s = self.f_search.get().strip().lower()
            if s and s not in q.title.lower() and s not in q.task().lower(): continue
            out.append(q)
        return out

    def sort_by(self, key):
        asc = not (self._sort[0] == key and self._sort[1])
        self._sort = (key, asc); self.refresh()

    def refresh(self):
        rows = self.filtered()
        key, asc = self._sort
        if key:
            def kf(q):
                v = getattr(q, key, "") if key not in ("items", "dirty") else (len(q.items) if key == "items" else q.dirty)
                return (v is None, v)
            try: rows = sorted(rows, key=kf, reverse=not asc)
            except TypeError: pass
        self.tree.delete(*self.tree.get_children())
        for q in rows:
            tags = []
            if q.dirty: tags.append("dirty")
            if q.money < 0 or q.gold < 0 or q.fame < 0: tags.append("neg")
            self.tree.insert("", "end", iid=q.path, tags=tags, values=(
                q.folder, q.npc, q.tier, q.title, q.money, q.gold, q.fame,
                q.xp, len(q.items), "*" if q.dirty else ""))
        ndirty = sum(1 for q in self.quests if q.dirty)
        self.lbl_count.config(text=f"{len(rows)} shown / {len(self.quests)} total")
        self.status.config(text=f"{ndirty} unsaved change(s)")

    def by_path(self, p):
        return next((q for q in self.quests if q.path == p), None)

    def on_select(self, _evt):
        sel = self.tree.selection()
        if not sel: return
        q = self.by_path(sel[0]); self._cur = q
        if not q: return
        self.ed_info.config(text=f"[{q.npc} T{q.tier}] {q.title}")
        self.ed_task.config(text="Task: " + q.task())
        self.ev["money"].set(str(q.money)); self.ev["gold"].set(str(q.gold)); self.ev["fame"].set(str(q.fame))
        for w in self.skill_frame.winfo_children(): w.destroy()
        self.skill_vars = []
        col = 0
        for p in q.pools:
            for s in p.get("Skills", []):
                var = tk.StringVar(value=str(s.get("Experience", 0)))
                ttk.Label(self.skill_frame, text=f"XP {s.get('Skill')}").grid(row=0, column=col, padx=(8, 2))
                ttk.Entry(self.skill_frame, textvariable=var, width=9).grid(row=0, column=col + 1)
                self.skill_vars.append((s, var)); col += 2

    def apply_single(self):
        q = self._cur
        if not q: return
        try:
            money = int(float(self.ev["money"].get())); gold = int(float(self.ev["gold"].get()))
            fame = int(float(self.ev["fame"].get()))
            skills = [(s, int(float(v.get()))) for s, v in self.skill_vars]
        except ValueError:
            messagebox.showerror("Error", "Please enter numbers only."); return
        if q.pools:
            p = q.pools[0]
            if "CurrencyNormal" in p or money: p["CurrencyNormal"] = money
            if "CurrencyGold" in p or gold:    p["CurrencyGold"] = gold
            if "Fame" in p or fame:            p["Fame"] = fame
        for s, val in skills: s["Experience"] = val
        q.dirty = True
        self.refresh()
        self.status.config(text=f"'{q.title}' updated (not saved yet).")

    def _bulk_targets(self):
        return self.quests if self.bulk_scope.get() == "all" else self.filtered()

    def apply_bulk(self, preview):
        fields = {k for k, v in self.bf.items() if v.get()}
        if not fields:
            messagebox.showwarning("Note", "No field selected."); return
        try:
            factor = float(self.b_factor.get()); offset = float(self.b_offset.get())
            round_to = int(float(self.b_round.get()))
        except ValueError:
            messagebox.showerror("Error", "Factor / offset / round must be numbers."); return
        targets = self._bulk_targets()
        if preview:
            sample = []
            for q in targets[:12]:
                nv = lambda v: q.preview_value(v, factor, offset, round_to)
                ch = []
                if "money" in fields and q.money: ch.append(f"{q.money}->{nv(q.money)}$")
                if "fame" in fields and q.fame:  ch.append(f"{q.fame}->{nv(q.fame)}F")
                if "gold" in fields and q.gold:  ch.append(f"{q.gold}->{nv(q.gold)}G")
                if "xp" in fields and q.xp:      ch.append(f"{q.xp}->{nv(q.xp)}xp")
                if ch: sample.append(f"- {q.title[:32]}: " + ", ".join(ch))
            messagebox.showinfo(
                f"Preview ({len(targets)} quests affected)",
                "Fields: " + ", ".join(sorted(fields)) +
                f"\nFormula: old x {factor} + {offset}" + (f", rounded to {round_to}" if round_to > 1 else "") +
                "\n\n" + ("\n".join(sample) if sample else "(no values in range)") +
                ("\n..." if len(targets) > 12 else ""))
            return
        if not messagebox.askyesno("Apply?",
            f"{len(targets)} quests, fields {sorted(fields)}\n"
            f"old x {factor} + {offset}"
            + (f", rounded to {round_to}" if round_to > 1 else "")
            + "\n\nChanges memory only - save later via 'Save ALL'."):
            return
        n = sum(1 for q in targets if q.scale(fields, factor, offset, round_to))
        self.refresh()
        self.status.config(text=f"Bulk change applied to {n} quests (unsaved).")

    def save_all(self):
        dirty = [q for q in self.quests if q.dirty]
        if not dirty:
            messagebox.showinfo("Nothing to do", "No changes."); return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bdir = os.path.abspath(os.path.join(OVERRIDE, os.pardir, f"Reward_Backup_{stamp}"))
        for q in dirty:
            dst = os.path.join(bdir, os.path.relpath(q.path, OVERRIDE))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(q.path, dst); q.save()
        self.refresh()
        messagebox.showinfo("Saved", f"{len(dirty)} file(s) saved.\nBackup of the originals:\n{bdir}")

    def reload(self):
        if any(q.dirty for q in self.quests) and not messagebox.askyesno(
                "Reload", "Discard unsaved changes?"):
            return
        self.quests = load_quests(); self.refresh()
        self.status.config(text="Reloaded.")


def main():
    global OVERRIDE
    root = tk.Tk(); root.withdraw()  # transient root for early dialogs
    OVERRIDE = locate_override()
    while not OVERRIDE:
        messagebox.showinfo("Select quest folder",
            "Could not find your SCUM quest 'Override' folder automatically.\n\n"
            "Please pick it (or the folder that contains it) in the next dialog.")
        chosen = filedialog.askdirectory(title="Select your SCUM quest 'Override' folder")
        if not chosen:
            root.destroy(); return
        OVERRIDE = normalize_override(chosen)
        if not OVERRIDE:
            messagebox.showwarning("No quests found",
                "That folder contains no quest .json files. Try again.")
    remember_override(OVERRIDE)
    root.destroy()

    App(load_quests()).mainloop()


if __name__ == "__main__":
    main()
