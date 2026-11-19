import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
sys.coinit_flags = 0
import subprocess
import json
from guard_engine import windows
from guard_engine.process_probe import ProcessProbe
from guard_engine.audio_probe import AudioProbe

powershell = Path(windows.system_directory()) / "WindowsPowerShell/v1.0/powershell.exe"
script = "$s=Get-AuthenticodeSignature -LiteralPath 'C:\\Program Files\\Tencent\\Weixin\\Weixin.exe'; @{valid=($s.Status -eq 'Valid');subject=$s.SignerCertificate.Subject}|ConvertTo-Json -Compress"
result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True)
print("SIGNATURE", result.returncode, result.stdout.decode(errors="replace"), result.stderr.decode(errors="replace"))
try:
    target = ProcessProbe().scan()
    print("TARGET", json.dumps(target.facts() if target else None))
except Exception as exc:
    print("TARGET_ERROR", repr(exc))
audio = AudioProbe()
print("AUDIO", json.dumps(audio.snapshot(set())))
