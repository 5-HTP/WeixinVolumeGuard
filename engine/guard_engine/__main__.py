import sys
sys.coinit_flags = 0

import gc
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import threading
import time

import psutil
from . import windows
from .audio_probe import AudioProbe
from .frida_session import HookSession
from .process_probe import ProcessProbe, ProbeError


class Controller:
    def __init__(self, send):
        self.send = send
        self.probe = ProcessProbe()
        self.audio = AudioProbe()
        self.hook = None
        self.target = None
        self.desired = False
        self.generation = 0
        self.sequence = 0
        self.state = "Disabled"
        self.reason = None
        self.idle_since = None
        self.stable_since = None
        self.last_levels = None
        self.fingerprint = None
        self.next_scan = 0
        self.next_renew = 0
        self.retry_at = 0
        self.failures = 0
        self.failure_key = None
        self.cleanup_failed = False
        self.parent = None
        self.parent_created = None
        self.heartbeat = time.monotonic()

    def report(self):
        self.sequence += 1
        self.send(dict(kind="state", generation=self.generation, sequence=self.sequence,
                       desiredEnabled=self.desired, state=self.state, reasonCode=self.reason,
                       wechat=self.target.facts() if self.target else dict(running=False, support="Unknown"),
                       hook={**(self.hook.stats if self.hook else {}),
                             "attached": bool(self.hook and not self.hook.dead),
                             "armed": bool(self.hook and self.state == "Enabled")}))

    def state_to(self, state, reason=None):
        if (state, reason) != (self.state, self.reason):
            logging.info("state=%s reason=%s", state, reason)
        self.state, self.reason = state, reason

    def cleanup(self):
        if self.cleanup_failed and self.hook is None and self.target is not None:
            if psutil.pid_exists(self.target.pid) and windows.creation_time(self.target.pid) == self.target.created:
                self.state_to("Error", "CleanupUnconfirmed")
                raise RuntimeError("CleanupUnconfirmed")
        self.state_to("CleaningUp")
        self.report()
        try:
            if self.hook:
                self.hook.close()
            self.cleanup_failed = False
        except Exception:
            self.cleanup_failed = True
            self.state_to("Error", "CleanupUnconfirmed")
            raise
        finally:
            self.hook = None
            self.idle_since = self.stable_since = self.last_levels = None
            self.fingerprint = None

    def set_desired(self, value):
        self.generation += 1
        self.desired = value
        self.failures = 0
        self.retry_at = 0
        self.next_scan = 0
        if self.hook or self.cleanup_failed:
            self.cleanup()
        self.state_to("CheckingCompatibility" if value else "Disabled")
        self.report()

    def tick(self):
        now = time.monotonic()
        if now - self.heartbeat > 5 or not psutil.pid_exists(self.parent) or windows.creation_time(self.parent) != self.parent_created:
            raise EOFError("ParentLost")
        if self.cleanup_failed:
            if self.target and psutil.pid_exists(self.target.pid) and windows.creation_time(self.target.pid) == self.target.created:
                self.state_to("Error", "CleanupUnconfirmed")
                self.report()
                return
            self.cleanup_failed=False
            self.target=None
            self.next_scan=0
        if now >= self.next_scan:
            self.next_scan = now + 2
            previous = (self.target.pid, self.target.created) if self.target else None
            target = self.probe.scan()
            identity = (target.pid, target.created) if target else None
            if previous != identity:
                if self.hook:
                    self.cleanup()
                self.idle_since = self.stable_since = None
                self.failures = 0
                self.retry_at = 0
            self.target = target
        if not self.desired:
            self.state_to("Disabled")
            return
        if not self.target:
            self.state_to("WaitingForWeixin")
            return
        if not self.target.profile:
            if self.hook:
                self.cleanup()
            self.state_to("Unsupported", self.target.reason)
            return
        if now < self.retry_at or self.failures >= 4:
            return
        related = {self.target.pid}
        try:
            related.update(p.pid for p in psutil.Process(self.target.pid).children(recursive=True))
        except psutil.NoSuchProcess:
            self.next_scan = 0
            return
        sample = self.audio.snapshot(related)
        if self.hook:
            if sample["fingerprint"] != self.fingerprint or self.hook.dead:
                self.cleanup()
                self.state_to("RecheckingAudio")
                return
            if now >= self.next_renew:
                self.hook.renew()
                self.next_renew = now + 1
                self.state_to("Enabled")
            return
        if not sample["outputCount"]:
            self.state_to("WaitingForAudioDevice")
            return
        if sample["active"]:
            self.idle_since = self.stable_since = None
            self.last_levels = None
            self.state_to("WaitingForRecordingIdle")
            return
        if self.idle_since is None:
            self.idle_since = now
        levels = sample["levels"]
        if self.last_levels is None or levels.keys() != self.last_levels.keys() or any(
                abs(levels[k] - self.last_levels[k]) > 0.0001 for k in levels):
            self.stable_since = now
        self.last_levels = levels
        if now - self.idle_since < 2 or now - self.stable_since < 1:
            self.state_to("WaitingForRecordingIdle")
            return
        self.state_to("Attaching")
        self.report()
        self.hook = HookSession(self.target, self.generation)
        # Check again after installation, before the first authorization.
        after = self.audio.snapshot(related)
        if after["active"] or after["fingerprint"] != sample["fingerprint"]:
            self.cleanup()
            self.state_to("WaitingForRecordingIdle")
            return
        self.fingerprint = after["fingerprint"]
        self.hook.renew()
        self.next_renew = now + 1
        self.state_to("Enabled")

    def failure(self, exc):
        code = exc.code if isinstance(exc, ProbeError) else "AgentSetupFailed"
        if isinstance(exc, PermissionError):
            code = "ProcessAccessDenied"
        if "AudioImplementationUnsupported" in str(exc):
            code = "AudioImplementationUnsupported"
        if "CleanupUnconfirmed" in str(exc):
            code = "CleanupUnconfirmed"
            self.cleanup_failed = True
        if self.hook:
            try:
                self.cleanup()
            except Exception:
                code = "CleanupUnconfirmed"
        if code in ("ModuleNotLoaded",):
            self.target = None
            self.state_to("CheckingCompatibility" if self.desired else "Disabled", code)
        else:
            self.state_to("Unsupported" if code == "AudioImplementationUnsupported" else "Error", code)
        self.failures += 1
        self.retry_at = time.monotonic() + [1, 3, 10, 30][min(self.failures - 1, 3)]
        logging.error("failure type=%s code=%s", type(exc).__name__, code)
        self.report()


def main():
    sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    sys.stdout.reconfigure(encoding="utf-8", errors="strict", line_buffering=True)
    data = os.environ.get("WVG_DATA_DIRECTORY")
    logdir = (Path(data) if data else Path(os.environ["LOCALAPPDATA"]) / "WeixinVolumeGuard") / "Logs"
    logdir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logdir / "engine.log", maxBytes=524288, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(message)s")
    messages = queue.Queue(maxsize=128)

    def reader():
        try:
            pending = b""
            while True:
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if len(line) > 65536:
                        raise ValueError("MessageTooLarge")
                    messages.put(json.loads(line.decode("utf-8")), timeout=2)
                if len(pending) > 65536:
                    raise ValueError("MessageTooLarge")
        except Exception:
            pass
        finally:
            messages.put(None)

    threading.Thread(target=reader, daemon=True).start()
    run_id = ""
    def send(payload):
        print(json.dumps(dict(protocol=1, runId=run_id, **payload), ensure_ascii=False, allow_nan=False))

    controller = None
    try:
        hello = messages.get(timeout=10)
        if not isinstance(hello, dict) or hello.get("kind") != "hello" or hello.get("protocol") != 1:
            raise ValueError("InvalidHandshake")
        parent = int(hello["parentPid"])
        if parent != psutil.Process().ppid() or windows.creation_time(parent) != str(hello["parentCreated"]):
            raise ValueError("InvalidParent")
        if windows.sid(parent) != windows.sid(os.getpid()):
            raise ValueError("InvalidOwner")
        run_id = str(hello["runId"])
        controller = Controller(send)
        controller.parent, controller.parent_created = parent, str(hello["parentCreated"])
        controller.desired = hello.get("desiredEnabled") is True
        send(dict(kind="hello", requestId=hello.get("requestId")))
        next_report = 0
        while True:
            try:
                message = messages.get(timeout=0.2)
            except queue.Empty:
                message = {}
            if message is None:
                break
            if message:
                if message.get("protocol") != 1 or message.get("runId") != run_id:
                    send(dict(kind="error", reasonCode="InvalidProtocol"))
                    continue
                kind = message.get("kind")
                if kind == "heartbeat":
                    controller.heartbeat = time.monotonic()
                elif kind == "setDesiredEnabled" and isinstance(message.get("value"), bool):
                    try:
                        controller.set_desired(message["value"])
                    except Exception as exc:
                        controller.failure(exc)
                elif kind == "shutdown":
                    break
                elif kind != "getState":
                    send(dict(kind="error", reasonCode="UnknownCommand"))
                    continue
            try:
                controller.tick()
            except EOFError:
                break
            except Exception as exc:
                controller.failure(exc)
            if time.monotonic() >= next_report:
                controller.report()
                next_report = time.monotonic() + 1
    except Exception as exc:
        logging.error("worker stopped type=%s", type(exc).__name__)
        send(dict(kind="error", reasonCode=exc.code if isinstance(exc,ProbeError) else "WorkerFailed"))
    finally:
        if controller:
            try:
                controller.cleanup()
                controller.audio.close()
                controller.state_to("Disabled")
                controller.report()
                send(dict(kind="shutdown", cleanupConfirmed=True))
            except Exception:
                send(dict(kind="shutdown", cleanupConfirmed=False))
        gc.collect()


if __name__ == "__main__":
    main()
