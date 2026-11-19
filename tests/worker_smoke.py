import sys
from pathlib import Path
import json
import os
import queue
import subprocess
import threading
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from guard_engine.windows import creation_time

executable = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts/engine/WeixinVolumeGuard.Engine/WeixinVolumeGuard.Engine.exe"
run_id = "smoke-" + str(os.getpid())
child = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
                         env={**os.environ, "PYTHONPATH": "", "PYTHONHOME": ""})
messages = queue.Queue()
events = []
threading.Thread(target=lambda: [messages.put(json.loads(line)) for line in child.stdout], daemon=True).start()
def send(kind, **values):
    child.stdin.write(json.dumps(dict(protocol=1, runId=run_id, kind=kind, **values)) + "\n")
    child.stdin.flush()
def until(predicate, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        send("heartbeat")
        try:
            event = messages.get(timeout=.4)
        except queue.Empty:
            continue
        events.append(event)
        if predicate(event):
            return event
    raise TimeoutError(events[-3:])
try:
    send("hello", parentPid=os.getpid(), parentCreated=creation_time(os.getpid()), desiredEnabled=False)
    until(lambda e: e["kind"] == "hello")
    state = until(lambda e: e["kind"] == "state" and e["wechat"]["running"])
    assert state["state"] == "Disabled" and not state["hook"]["attached"]
    print("FROZEN_DISABLED", json.dumps(state), flush=True)
    if "--live" in sys.argv:
        send("setDesiredEnabled", value=True)
        enabled = until(lambda e: e["kind"] == "state" and e["state"] == "Enabled",30)
        assert enabled["hook"]["armed"]
        print("LIVE_ENABLED", json.dumps(enabled), flush=True)
        send("setDesiredEnabled", value=False)
        disabled = until(lambda e: e["kind"] == "state" and e["state"] == "Disabled" and e["generation"] >= 2)
        print("LIVE_DISABLED", json.dumps(disabled), flush=True)
    send("shutdown")
    result = until(lambda e: e["kind"] == "shutdown")
    assert result["cleanupConfirmed"]
    child.wait(timeout=5)
    assert child.returncode == 0
finally:
    if child.poll() is None:
        child.stdin.close()
        try: child.wait(timeout=8)
        except subprocess.TimeoutExpired: child.terminate(); child.wait(timeout=3)
    errors = child.stderr.read()
    if errors: print("STDERR", errors[:1500])
    (ROOT / "artifacts/evidence/worker-smoke.json").write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding="utf-8")
