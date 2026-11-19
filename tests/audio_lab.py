"""Bounded integration test. Only writes a non-default, idle test endpoint."""
import sys
sys.coinit_flags = 0
import json
import queue
from pathlib import Path
import subprocess
import threading
import time
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import frida
from pycaw.pycaw import AudioUtilities, IAudioSessionControl2
from guard_engine.windows import system_directory, creation_time


def main():
    devices = [d for d in AudioUtilities.GetAllDevices() if d.state.name == "Active"]
    enum = AudioUtilities.GetDeviceEnumerator()
    defaults = {enum.GetDefaultAudioEndpoint(0, r).GetId() for r in range(3)}
    candidates = [d for d in devices if d.id.startswith("{0.0.0.") and d.id not in defaults]
    print("CANDIDATES", [(d.FriendlyName, d.id) for d in candidates], flush=True)
    # The original authorized lab used this otherwise unconnected hardware channel.
    device = next(d for d in candidates if "7/8" in d.FriendlyName)
    sessions = device.AudioSessionManager.GetSessionEnumerator()
    assert all(sessions.GetSession(i).QueryInterface(IAudioSessionControl2).GetState() != 1
               for i in range(sessions.GetCount())), "EndpointInUse"
    volume = device.EndpointVolume
    baseline = volume.GetMasterVolumeLevelScalar()
    baseline_db = volume.GetMasterVolumeLevel()
    mute = volume.GetMute()
    value = baseline - .03 if baseline >= .05 else baseline + .03
    low, high, step = volume.GetVolumeRange()
    db_value = baseline_db - max(1, step) if baseline_db > low + max(1, step) else baseline_db + max(1, step)
    results = []
    secondary_volume = None
    secondary_baseline = None
    child = None
    session = None
    script = None
    lines = queue.Queue()
    def record(name, passed, evidence):
        results.append(dict(id=name, result="PASS" if passed else "FAIL", evidence=evidence))
        print(name, results[-1]["result"], evidence, flush=True)
        assert passed, name
    try:
        child = subprocess.Popen([str(ROOT / "artifacts/AudioLab.exe"), device.id], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=lambda: [lines.put(line.strip()) for line in child.stdout], daemon=True).start()
        ready = lines.get(timeout=8)
        assert ready.startswith("READY "), ready
        scalar_address = "0x" + ready.split()[1]
        def call(command, val=0):
            child.stdin.write(command + str(val) + "\n"); child.stdin.flush()
            return json.loads(lines.get(timeout=5))
        before = call("t", value)
        record("E01", abs(before["scalar"] - baseline) > .01, before)
        call("t", baseline)
        session = frida.attach(child.pid, persist_timeout=0)
        observed = queue.Queue()
        observer = session.create_script("Interceptor.attach(ptr('" + scalar_address + "'), {onEnter() { send({caller:this.returnAddress.toString()}); }}); rpc.exports.info=()=>{const m=Process.getModuleByName('AudioLab.exe');return {base:m.base.toString(),path:m.path};};")
        observer.on("message", lambda msg, data: observed.put(msg["payload"]) if msg.get("type") == "send" else None)
        observer.load()
        info = observer.exports_sync.info()
        call("t", baseline); caller = observed.get(timeout=3)["caller"]
        call("n", baseline); other_caller = observed.get(timeout=3)["caller"]
        assert caller != other_caller
        observer.unload()
        config = dict(generation=1, moduleName="AudioLab.exe", modulePath=info["path"], moduleBase=info["base"],
                      returnRva=int(caller, 16) - int(info["base"], 16), systemDirectory=system_directory())
        source = (ROOT / "engine/guard_engine/resources/agent.js").read_text(encoding="utf-8")
        script = session.create_script(source)
        script.load()
        setup = script.exports_sync.setup(config)
        script.exports_sync.renew(1)
        result = call("t", value)
        stats = script.exports_sync.status()
        record("E02", result["hr"] == 0 and abs(result["scalar"] - baseline) < .001 and stats["blockedCount"] >= 1,
               dict(readback=result, stats=stats, targetCaller=caller))
        second = next(d for d in candidates if d.id != device.id)
        second_sessions = second.AudioSessionManager.GetSessionEnumerator()
        assert all(second_sessions.GetSession(i).QueryInterface(IAudioSessionControl2).GetState()!=1 for i in range(second_sessions.GetCount()))
        secondary_volume=second.EndpointVolume
        secondary_baseline=secondary_volume.GetMasterVolumeLevelScalar()
        second_value=secondary_baseline-.03 if secondary_baseline>=.05 else secondary_baseline+.03
        call("s",second.id)
        boundary=call("t",second_value)
        record("B01",abs(boundary["scalar"]-secondary_baseline)<.001,
               dict(device=second.FriendlyName,readback=boundary,sameCallerAlsoBlocked=True))
        secondary_volume.SetMasterVolumeLevelScalar(secondary_baseline,None)
        call("p")
        result = call("n", value)
        record("E03", abs(result["scalar"] - baseline) > .01, dict(readback=result, otherCaller=other_caller))
        call("n", baseline)
        result = call("d", db_value)
        record("E04", abs(result["db"] - db_value) < max(.11, step / 2), result)
        volume.SetMasterVolumeLevelScalar(baseline, None)
        volume.SetMasterVolumeLevelScalar(value, None)
        record("E05", abs(volume.GetMasterVolumeLevelScalar() - baseline) > .01,
               dict(scalar=volume.GetMasterVolumeLevelScalar()))
        volume.SetMasterVolumeLevelScalar(baseline, None)
        ack = script.exports_sync.cleanup()
        script.unload(); script = None
        result = call("t", value)
        record("E06", ack["targetCount"] == 0 and abs(result["scalar"] - baseline) > .01, dict(ack=ack, readback=result))
        call("t", baseline)
        script = session.create_script(source.replace("timer=setInterval(function()", "throw new Error('InjectedSetupFailure'); timer=setInterval(function()"))
        script.load()
        failed = False
        try:
            script.exports_sync.setup(config)
        except frida.RPCException:
            failed = True
        status = script.exports_sync.status()
        result = call("t", value)
        record("E07", failed and status["targetCount"] == 0 and abs(result["scalar"] - baseline) > .01,
               dict(status=status, readback=result, fault="exception after replacement before ready"))
        script.unload(); script = None
        call("t", baseline)
        host = subprocess.Popen([sys.executable, str(ROOT / "tests/hook_host.py"), str(child.pid), json.dumps(config)],
                                stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        host_lines = queue.Queue()
        threading.Thread(target=lambda: [host_lines.put(line.strip()) for line in host.stdout],daemon=True).start()
        try:
            assert host_lines.get(timeout=8) == "READY"
            assert abs(call("t",value)["scalar"]-baseline)<.001
            crash_started=time.monotonic()
            host.kill(); host.wait(timeout=5)
            restored_after_crash=False
            while time.monotonic()-crash_started<8:
                result=call("t",value)
                if abs(result["scalar"]-baseline)>.01:
                    restored_after_crash=True;break
                time.sleep(.2)
            record("E08",restored_after_crash,dict(seconds=round(time.monotonic()-crash_started,2),readback=result))
        finally:
            if host.poll() is None: host.kill();host.wait(timeout=3)
            call("t",baseline)
        stale_rejected=True
        for cycle in range(3):
            script=session.create_script(source);script.load();script.exports_sync.setup(config);script.exports_sync.renew(1)
            script.exports_sync.cleanup()
            try:
                script.exports_sync.renew(1);stale_rejected=False
            except frida.RPCException:
                pass
            script.unload();script=None
        result=call("t",value)
        record("E10",stale_rejected and abs(result["scalar"]-baseline)>.01,dict(cycles=3,staleRenewRejected=stale_rejected,readback=result))
        call("t",baseline)
        script = session.create_script(source); script.load(); script.exports_sync.setup(config); script.exports_sync.renew(1)
        start = time.monotonic()
        time.sleep(5.6)
        result = call("t", value)
        status = script.exports_sync.status()
        record("E09", not status["armed"] and abs(result["scalar"] - baseline) > .01,
               dict(seconds=round(time.monotonic()-start,2), status=status, readback=result))
        script.unload(); script = None
        call("t", baseline)
        fault_source=source.replace("this.returnAddress.equals(expectedReturn)","(function(){throw new Error('InjectedFilterFailure');})()")
        script=session.create_script(fault_source);script.load();script.exports_sync.setup(config);script.exports_sync.renew(1)
        result=call("t",value)
        status=script.exports_sync.status()
        refused=False
        try:script.exports_sync.renew(1)
        except frida.RPCException:refused=True
        record("B02",not status["armed"] and bool(status["error"]) and refused and abs(result["scalar"]-baseline)>.01,
               dict(status=status,renewRejected=refused,readback=result))
        script.exports_sync.cleanup();script.unload();script=None
        call("t",baseline)
        old_identity=(child.pid,creation_time(child.pid))
        child.stdin.write("q\n");child.stdin.flush();child.wait(timeout=5)
        child=subprocess.Popen([str(ROOT / "artifacts/AudioLab.exe"),device.id],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        lines=queue.Queue()
        threading.Thread(target=lambda:[lines.put(line.strip()) for line in child.stdout],daemon=True).start()
        assert lines.get(timeout=5).startswith("READY ")
        new_identity=(child.pid,creation_time(child.pid))
        result=call("t",value)
        record("E11",old_identity!=new_identity and abs(result["scalar"]-baseline)>.01,
               dict(oldIdentity=old_identity,newIdentity=new_identity,readback=result))
        call("t",baseline)
    finally:
        if script:
            try: script.unload()
            except Exception: pass
        if session:
            try: session.detach()
            except Exception: pass
        if child and child.poll() is None:
            try:
                child.stdin.write("q\n"); child.stdin.flush(); child.wait(timeout=5)
            except Exception:
                child.terminate(); child.wait(timeout=3)
        volume.SetMasterVolumeLevelScalar(baseline, None)
        volume.SetMute(mute, None)
        if secondary_volume is not None:
            secondary_volume.SetMasterVolumeLevelScalar(secondary_baseline,None)
            assert abs(secondary_volume.GetMasterVolumeLevelScalar()-secondary_baseline)<.001
        restored = dict(scalar=volume.GetMasterVolumeLevelScalar(), db=volume.GetMasterVolumeLevel(), mute=volume.GetMute())
        results.append(dict(id="E12", result="PASS" if abs(restored["scalar"]-baseline)<.001 and abs(restored["db"]-baseline_db)<.11 and restored["mute"]==mute else "FAIL", evidence=restored))
        report = dict(device=device.FriendlyName, endpointId=device.id, baselineScalar=baseline, baselineDb=baseline_db,
                      restored=restored, cases=results)
        (ROOT / "artifacts/evidence/audio-lab.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("RESTORED", restored, flush=True)


if __name__ == "__main__":
    main()
