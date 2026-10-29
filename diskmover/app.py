"""Tkinter desktop UI for Disk Mover."""
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import core


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Disk Mover - user files dusre drive me shift karein")
        self.geometry("720x560")
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.items = []
        self.busy = False

        pad = {"padx": 10, "pady": 4}
        ttk.Label(self, text="Source folders (inhi ki files move hongi):").pack(anchor="w", **pad)
        f = ttk.Frame(self); f.pack(fill="x", **pad)
        self.src_list = tk.Listbox(f, height=6, selectmode="extended")
        self.src_list.pack(side="left", fill="x", expand=True)
        for s in core.default_sources():
            self.src_list.insert("end", s)
        b = ttk.Frame(f); b.pack(side="left", padx=6)
        ttk.Button(b, text="Add folder", command=self.add_src).pack(fill="x")
        ttk.Button(b, text="Remove", command=self.rm_src).pack(fill="x", pady=2)

        ttk.Label(self, text="Destination folder (files yaha shift hongi):").pack(anchor="w", **pad)
        d = ttk.Frame(self); d.pack(fill="x", **pad)
        self.dest = tk.StringVar()
        ttk.Entry(d, textvariable=self.dest).pack(side="left", fill="x", expand=True)
        ttk.Button(d, text="Browse", command=self.pick_dest).pack(side="left", padx=6)

        ttk.Label(self, text="System/important files (Windows, Program Files, AppData, system-flag files) "
                  "hamesha chhod di jati hain.", foreground="#555").pack(anchor="w", **pad)

        a = ttk.Frame(self); a.pack(fill="x", **pad)
        self.btn_scan = ttk.Button(a, text="1. Preview (scan)", command=self.do_scan)
        self.btn_move = ttk.Button(a, text="2. Move files", command=self.do_move, state="disabled")
        self.btn_undo = ttk.Button(a, text="Undo last move", command=self.do_undo)
        self.btn_cancel = ttk.Button(a, text="Cancel", command=self.cancel.set, state="disabled")
        for w in (self.btn_scan, self.btn_move, self.btn_undo, self.btn_cancel):
            w.pack(side="left", padx=3)

        self.bar = ttk.Progressbar(self, mode="determinate"); self.bar.pack(fill="x", **pad)
        self.status = tk.StringVar(value="Source aur destination chuniye, phir Preview dabaiye.")
        ttk.Label(self, textvariable=self.status).pack(anchor="w", **pad)
        self.log = tk.Text(self, height=12, state="disabled"); self.log.pack(fill="both", expand=True, **pad)
        self.after(100, self.poll)

    # ---- helpers
    def sources(self):
        return list(self.src_list.get(0, "end"))

    def add_src(self):
        p = filedialog.askdirectory(title="Source folder")
        if p and p not in self.sources():
            self.src_list.insert("end", os.path.normpath(p))

    def rm_src(self):
        for i in reversed(self.src_list.curselection()):
            self.src_list.delete(i)

    def pick_dest(self):
        p = filedialog.askdirectory(title="Destination folder")
        if p:
            self.dest.set(os.path.normpath(p))

    def write(self, text):
        self.log.config(state="normal"); self.log.insert("end", text + "\n")
        self.log.see("end"); self.log.config(state="disabled")

    def set_busy(self, busy):
        self.busy = busy
        self.cancel.clear()
        st = "disabled" if busy else "normal"
        self.btn_scan.config(state=st); self.btn_undo.config(state=st)
        self.btn_cancel.config(state="normal" if busy else "disabled")
        if busy:
            self.btn_move.config(state="disabled")

    def run_thread(self, fn):
        self.set_busy(True)
        threading.Thread(target=fn, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, *a = self.q.get_nowait()
                if kind == "progress":
                    done, total, name = a
                    self.bar.config(maximum=max(total, 1), value=done)
                    self.status.set(f"{done}/{total}  {os.path.basename(name)}")
                elif kind == "log":
                    self.write(a[0])
                elif kind == "status":
                    self.status.set(a[0])
                elif kind == "scan_done":
                    self.set_busy(False)
                    self.items = a[0]
                    self.btn_move.config(state="normal" if self.items else "disabled")
                elif kind == "done":
                    self.set_busy(False)
                    self.items = []
        except queue.Empty:
            pass
        self.after(100, self.poll)

    # ---- actions
    def do_scan(self):
        err = core.validate(self.sources(), self.dest.get())
        if err:
            return messagebox.showerror("Error", err)
        srcs, dest = self.sources(), self.dest.get()
        self.write("Scanning...")

        def work():
            items = []
            for it in core.scan(srcs, dest, self.cancel):
                items.append(it)
                if len(items) % 200 == 0:
                    self.q.put(("status", f"{len(items)} files mili..."))
            total = sum(i.size for i in items)
            free = core.free_space(dest)
            self.q.put(("log", f"{len(items)} files, {core.fmt_size(total)} move hongi. "
                               f"Destination me khali jagah: {core.fmt_size(free)}"))
            if total > free:
                self.q.put(("log", "WARNING: destination me itni jagah nahi hai."))
                items = []
            self.q.put(("status", "Preview ready. Move files dabaiye." if items else "Kuch move karne ko nahi."))
            self.q.put(("scan_done", items))
        self.run_thread(work)

    def do_move(self):
        if not messagebox.askyesno("Confirm", f"{len(self.items)} files move karni hain. Aage badhein?\n"
                                   "(Baad me 'Undo last move' se wapas la sakte hain.)"):
            return
        items, dest = self.items, self.dest.get()

        def work():
            moved, failed = core.execute(items, dest, lambda *a: self.q.put(("progress", *a)), self.cancel)
            self.q.put(("log", f"Moved: {len(moved)}, Failed: {len(failed)}"))
            for p, e in failed[:50]:
                self.q.put(("log", f"  skip: {p} ({e})"))
            self.q.put(("status", "Ho gaya."))
            self.q.put(("done",))
        self.run_thread(work)

    def do_undo(self):
        dest = self.dest.get() or filedialog.askdirectory(title="Jis destination me files shift hui thi")
        if not dest:
            return
        self.dest.set(dest)

        def work():
            try:
                n, failed = core.undo(dest, lambda *a: self.q.put(("progress", *a)), self.cancel)
                self.q.put(("log", f"Restored: {n}, Failed: {len(failed)}"))
            except FileNotFoundError as e:
                self.q.put(("log", str(e)))
            self.q.put(("status", "Undo complete."))
            self.q.put(("done",))
        self.run_thread(work)


def main():
    App().mainloop()
