"""Timed, opt-in metadata-only trial. Never opens, records or sends a voice message."""
import sys
sys.coinit_flags = 0
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
from guard_engine.process_probe import ProcessProbe
from guard_engine.audio_probe import AudioProbe
from pycaw.pycaw import AudioUtilities

executable = Path(sys.argv[1])
mode = sys.argv[2] if len(sys.argv) > 2 else "protected"
target = ProcessProbe().scan()
assert target and target.profile
import psutil
related = {target.pid} | {p.pid for p in psutil.Process(target.pid).children(recursive=True)}
audio = AudioProbe()
volume = AudioUtilities.GetSpeakers().EndpointVolume
baseline = float(volume.GetMasterVolumeLevel())
run_id = "trial-" + str(os.getpid())
child = subprocess.Popen([str(executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW)
messages = queue.Queue()
events, samples = [], []
threading.Thread(target=lambda: [messages.put(json.loads(line)) for line in child.stdout],daemon=True).start()
def send(kind, **values):
    child.stdin.write(json.dumps(dict(protocol=1,runId=run_id,kind=kind,**values))+"\n");child.stdin.flush()
start = time.monotonic()
last_heartbeat = 0
capture_started = None
capture_ended = None
enabled = False
activation_requested = False
wait_seen = False
result = "NOT_TRIGGERED"
end_state = None
try:
    send("hello",parentPid=os.getpid(),parentCreated=creation_time(os.getpid()),desiredEnabled=(mode=="protected"))
    if mode == "during":
        print("TRIAL_READY_START_RECORDING",mode,"maximum_seconds=180",flush=True)
    announced = False
    while time.monotonic()-start < 180:
        elapsed=time.monotonic()-start
        if elapsed-last_heartbeat>=.7:
            send("heartbeat");last_heartbeat=elapsed
        while not messages.empty():
            event=messages.get_nowait();events.append(event)
            if event["kind"]=="state":
                state=event["state"]
                if state=="WaitingForRecordingIdle" and activation_requested: wait_seen=True
                if state=="Enabled":
                    enabled=True
                    if mode=="protected" and not announced:
                        print("TRIAL_READY_START_RECORDING",mode,"maximum_seconds=180",flush=True);announced=True
                    if mode=="during" and capture_ended is not None:
                        end_state=event
        snapshot=audio.snapshot(related)
        db=float(volume.GetMasterVolumeLevel())
        samples.append(dict(seconds=round(elapsed,2),db=round(db,4),capture=snapshot["active"]))
        if snapshot["active"] and capture_started is None:
            capture_started=elapsed;print("CAPTURE_START",round(elapsed,2),flush=True)
        if mode=="during" and capture_started is not None and not activation_requested and elapsed-capture_started>=1:
            send("setDesiredEnabled",value=True);activation_requested=True;print("ENABLE_DURING_CAPTURE",round(elapsed,2),flush=True)
        if capture_started is not None and not snapshot["active"] and capture_ended is None:
            capture_ended=elapsed;print("CAPTURE_END",round(elapsed,2),flush=True)
        if capture_ended is not None and elapsed-capture_ended>=8:
            blocked=max([e.get("hook",{}).get("blockedCount",0) for e in events if e["kind"]=="state"] or [0])
            stable=all(abs(s["db"]-baseline)<.15 for s in samples)
            if mode=="protected":
                result="PASS" if enabled and blocked>0 and stable else "FAIL"
            else:
                result="PASS" if wait_seen and end_state is not None and abs(db-baseline)<.15 else "FAIL"
            break
        time.sleep(.1)
finally:
    try:
        send("shutdown")
        end=time.monotonic()+10
        confirmed=False
        while time.monotonic()<end:
            try: e=messages.get(timeout=.2)
            except queue.Empty: continue
            events.append(e)
            if e["kind"]=="shutdown": confirmed=e["cleanupConfirmed"];break
        child.stdin.close();child.wait(timeout=5)
    except Exception:
        confirmed=False
        if child.poll() is None: child.terminate();child.wait(timeout=3)
    report=dict(mode=mode,result=result,baselineDb=baseline,finalDb=float(volume.GetMasterVolumeLevel()),
                cleanupConfirmed=confirmed,captureStarted=capture_started,captureEnded=capture_ended,events=events,samples=samples)
    (ROOT/f"artifacts/evidence/recording-{mode}.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("TRIAL_ENDED",result,"cleanupConfirmed="+str(confirmed),"finalDb="+str(report["finalDb"]),flush=True)
