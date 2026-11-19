"""Crash-test host; launched and terminated only by audio_lab.py."""
import json
from pathlib import Path
import sys
import time
import frida

root = Path(__file__).resolve().parents[1]
session = frida.attach(int(sys.argv[1]), persist_timeout=0)
script = session.create_script((root / "engine/guard_engine/resources/agent.js").read_text(encoding="utf-8"))
script.load()
config = json.loads(sys.argv[2])
script.exports_sync.setup(config)
script.exports_sync.renew(config["generation"])
print("READY", flush=True)
while True:
    script.exports_sync.renew(config["generation"])
    time.sleep(1)
