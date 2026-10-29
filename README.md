# Disk Mover

Windows desktop app jo user ki files (Desktop, Documents, Downloads, Pictures, Videos, Music)
dusre drive/folder me shift karta hai. Windows, Program Files, ProgramData, AppData, OneDrive aur
system-flag wali files kabhi nahi chhuta.

- Pehle **Preview** (kuch move nahi hota), phir **Move files**.
- Folder structure destination me `<dest>\<FolderName>\...` ban jata hai.
- Same naam ki file ho to overwrite nahi hoti, `name (1).ext` ban jata hai.
- Har move `diskmover_manifest.json` (destination me) me save hota hai, **Undo last move** se sab wapas.

## Run
```
python run.py
```
Python 3.9+ chahiye, koi extra package nahi.

## .exe banana
```
pip install pyinstaller
pyinstaller --onefile --windowed --name DiskMover run.py
```
`dist\DiskMover.exe` ban jayega.

## Tests
```
python -m unittest discover tests
```
