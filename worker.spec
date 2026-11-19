from PyInstaller.utils.hooks import collect_all
from pathlib import Path

root = Path(SPECPATH)
datas, binaries, hiddenimports = [], [], []
for name in ('frida', 'pycaw', 'comtypes'):
    d, b, h = collect_all(name)
    datas += d
    binaries += b
    hiddenimports += h
datas += [(str(root / 'guard_engine/resources/agent.js'), 'guard_engine/resources')]
a = Analysis([str(root / 'worker.py')], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='WeixinVolumeGuard.Engine',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='WeixinVolumeGuard.Engine')
