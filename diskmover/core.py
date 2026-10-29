"""Core logic: scan user files, plan the move, execute it, undo it.

No GUI code here so it can be tested anywhere.
"""
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

# Folders directly inside the user profile that hold *user* data.
USER_FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"]

# Names that are never touched, wherever they appear.
PROTECTED_DIR_NAMES = {
    "windows", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "appdata", "application data",
    "local settings", "onedrive", "node_modules", ".git",
}
PROTECTED_FILE_NAMES = {"desktop.ini", "thumbs.db", "ntuser.dat", "pagefile.sys",
                        "hiberfil.sys", "swapfile.sys"}
PROTECTED_FILE_PREFIXES = ("ntuser.", "~$")

FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
MANIFEST_NAME = "diskmover_manifest.json"


@dataclass
class Item:
    src: str
    dst: str
    size: int


def default_sources():
    home = Path.home()
    return [str(home / f) for f in USER_FOLDERS if (home / f).is_dir()]


def _attrs(path):
    try:
        return getattr(os.stat(path, follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return 0


def is_protected_file(name, path):
    low = name.lower()
    if low in PROTECTED_FILE_NAMES or low.startswith(PROTECTED_FILE_PREFIXES):
        return True
    return bool(_attrs(path) & FILE_ATTRIBUTE_SYSTEM)


def is_protected_dir(name, path):
    if name.lower() in PROTECTED_DIR_NAMES:
        return True
    a = _attrs(path)
    return bool(a & (FILE_ATTRIBUTE_SYSTEM | FILE_ATTRIBUTE_REPARSE_POINT)) or os.path.islink(path)


def _inside(child, parent):
    child, parent = os.path.normcase(os.path.abspath(child)), os.path.normcase(os.path.abspath(parent))
    return child == parent or child.startswith(parent + os.sep)


def _unique(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def scan(sources, dest, cancel=None):
    """Yield Items for every movable file under sources. dest is never scanned."""
    for src_root in sources:
        label = os.path.basename(os.path.normpath(src_root)) or "root"
        for dirpath, dirnames, filenames in os.walk(src_root, followlinks=False):
            if cancel and cancel.is_set():
                return
            dirnames[:] = [d for d in dirnames
                           if not is_protected_dir(d, os.path.join(dirpath, d))
                           and not _inside(os.path.join(dirpath, d), dest)]
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                if is_protected_file(fn, p) or os.path.islink(p):
                    continue
                try:
                    size = os.path.getsize(p)
                except OSError:
                    continue
                rel = os.path.relpath(p, src_root)
                yield Item(p, os.path.join(dest, label, rel), size)


def validate(sources, dest):
    if not dest:
        return "Destination folder chuniye."
    if not sources:
        return "Kam se kam ek source folder chuniye."
    for s in sources:
        if _inside(dest, s):
            return f"Destination source ke andar nahi ho sakta: {s}"
    return None


def execute(items, dest, progress=None, cancel=None):
    """Move items, write a manifest for undo. Returns (moved, failed list)."""
    os.makedirs(dest, exist_ok=True)
    moved, failed = [], []
    total = len(items)
    for i, it in enumerate(items, 1):
        if cancel and cancel.is_set():
            break
        try:
            target = _unique(it.dst)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(it.src, target)
            moved.append({"src": it.src, "dst": target})
        except OSError as e:
            failed.append((it.src, str(e)))
        if progress:
            progress(i, total, it.src)
    manifest = os.path.join(dest, MANIFEST_NAME)
    existing = []
    if os.path.exists(manifest):
        with open(manifest, encoding="utf-8") as f:
            existing = json.load(f).get("moves", [])
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "moves": existing + moved}, f, indent=1)
    return moved, failed


def undo(dest, progress=None, cancel=None):
    """Move everything in the manifest back to its original place."""
    manifest = os.path.join(dest, MANIFEST_NAME)
    if not os.path.exists(manifest):
        raise FileNotFoundError("Is folder me koi manifest nahi mila.")
    with open(manifest, encoding="utf-8") as f:
        moves = json.load(f)["moves"]
    restored, failed, remaining = 0, [], []
    for i, m in enumerate(moves, 1):
        if cancel and cancel.is_set():
            remaining.extend(moves[i - 1:])
            break
        try:
            if not os.path.exists(m["dst"]):
                raise FileNotFoundError("file ab destination me nahi hai")
            back = _unique(m["src"])
            os.makedirs(os.path.dirname(back), exist_ok=True)
            shutil.move(m["dst"], back)
            restored += 1
        except OSError as e:
            failed.append((m["dst"], str(e)))
            remaining.append(m)
        if progress:
            progress(i, len(moves), m["dst"])
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "moves": remaining}, f, indent=1)
    return restored, failed


def free_space(path):
    p = path
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return shutil.disk_usage(p or ".").free


def fmt_size(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.1f} {u}" if u != "B" else f"{n} B"
        n /= 1024
