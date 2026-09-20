#!/usr/bin/env python3
"""
Gera o executável (PyInstaller) e o instalador (Inno Setup).

    python build.py            # exe + instalador (se o Inno Setup estiver instalado)
    python build.py --exe-only # só o executável em dist/SistemaSolar/

Requisitos: pip install pyinstaller pygame numpy   |   Inno Setup 6 (https://jrsoftware.org/isinfo.php)
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VERSION = "1.0.0"


def find_iscc():
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return found
    candidates = [
        os.path.join(os.environ.get(v, ""), "Inno Setup 6", "ISCC.exe")
        for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")
    ] + glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup*", "ISCC.exe"))
    return next((c for c in candidates if os.path.isfile(c)), None)


def run(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe-only", action="store_true")
    args = ap.parse_args()

    run([sys.executable, os.path.join("packaging", "make_icon.py")])
    for d in ("build", "dist"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
         "--name", "SistemaSolar", "--icon", os.path.join(ROOT, "packaging", "icon.ico"),
         "--specpath", os.path.join(ROOT, "build"), "--workpath", os.path.join(ROOT, "build", "pyi"), "--distpath", os.path.join(ROOT, "dist"),
         "--exclude-module", "tkinter", "--exclude-module", "unittest", "--exclude-module", "pydoc",
         os.path.join(ROOT, "sistema_solar.py")])
    print("\nExecutável:", os.path.join(ROOT, "dist", "SistemaSolar", "SistemaSolar.exe"))

    if args.exe_only:
        return
    iscc = find_iscc()
    if not iscc:
        print("\nInno Setup não encontrado — instalador não gerado.\n"
              "Instale com:  winget install JRSoftware.InnoSetup   e rode  python build.py  de novo.")
        return
    run([iscc, f"/DAppVersion={VERSION}", os.path.join("packaging", "installer.iss")])
    print("\nInstalador:", os.path.join(ROOT, "installer", f"SistemaSolar_Setup_{VERSION}.exe"))


if __name__ == "__main__":
    main()
