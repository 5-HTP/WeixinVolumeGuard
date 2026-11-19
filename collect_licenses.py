from pathlib import Path
import importlib.metadata as metadata
import shutil
import sys

destination = Path(sys.argv[1]) / "Licenses"
destination.mkdir(parents=True, exist_ok=True)
for name in ("frida", "psutil", "pycaw", "comtypes", "pyinstaller", "pyinstaller-hooks-contrib"):
    dist = metadata.distribution(name)
    target = destination / (name + "-" + dist.version)
    target.mkdir(exist_ok=True)
    (target / "METADATA.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
    for file in dist.files or []:
        if any(word in file.name.lower() for word in ("license", "copying", "notice")):
            source = Path(dist.locate_file(file))
            if source.is_file():
                shutil.copy2(source, target / file.name)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    shutil.copy2(python_license, destination / "Python-LICENSE.txt")
