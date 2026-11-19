from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import ctypes

import psutil
from . import windows
from .profiles import match_profile


class ProbeError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass
class Target:
    pid: int
    created: str
    path: str
    base: int
    version: str
    digest: str
    file_id: tuple
    profile: object
    reason: str | None

    def facts(self):
        return dict(running=True, pid=self.pid, creationTime100ns=self.created,
                    fileVersion=self.version, profileId=self.profile.id if self.profile else None,
                    support="Supported" if self.profile else "Unsupported", reasonCode=self.reason)


class ProcessProbe:
    def __init__(self):
        native_info=ctypes.create_string_buffer(64)
        windows.kernel.GetNativeSystemInfo(ctypes.byref(native_info))
        if ctypes.cast(native_info,ctypes.POINTER(ctypes.c_ushort))[0] != 9:
            raise ProbeError("UnsupportedArchitecture")
        self.owner_sid = windows.sid(os.getpid())
        self.session = windows.session_id(os.getpid())
        self.cached = None
        self.signed = {}

    def verify_publisher(self, path):
        identity = windows.file_identity(path)
        if self.signed.get(path) == identity:
            return
        # No shell interpolation: pass the file path as a PowerShell script argument.
        quoted_path = "'" + path.replace("'", "''") + "'"
        script = ("$s=Get-AuthenticodeSignature -LiteralPath " + quoted_path + "; "
                  "@{valid=($s.Status -eq 'Valid');subject=$s.SignerCertificate.Subject}|ConvertTo-Json -Compress")
        powershell = Path(windows.system_directory()) / "WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
                                env={**os.environ, "PSModulePath": str(powershell.parent / "Modules")})
        try:
            data = json.loads(result.stdout.decode("utf-8-sig"))
            valid = data["valid"] and "O=Tencent Technology (Shenzhen) Company Limited" in data["subject"]
        except (ValueError, KeyError, TypeError, UnicodeError):
            valid = False
        if not valid:
            raise ProbeError("PublisherUnverified")
        if identity != windows.file_identity(path):
            raise ProbeError("ModuleChanged")
        self.signed[path] = identity

    def scan(self):
        candidates = []
        for process in psutil.process_iter(["pid", "name"]):
            if (process.info["name"] or "").lower() != "weixin.exe":
                continue
            try:
                if windows.session_id(process.pid) != self.session or windows.sid(process.pid) != self.owner_sid:
                    continue
                if any(arg.startswith("--type=") for arg in process.cmdline()):
                    continue
                if any(parent.name().lower() == "weixin.exe" for parent in process.parents()):
                    continue
                candidates.append(process)
            except (psutil.NoSuchProcess, ProcessLookupError):
                continue
            except (psutil.AccessDenied, PermissionError):
                raise ProbeError("ProcessAccessDenied")
        if not candidates:
            self.cached = None
            return None
        if len(candidates) != 1:
            raise ProbeError("AmbiguousMainProcess")
        process = candidates[0]
        created = windows.creation_time(process.pid)
        self.verify_publisher(process.exe())
        matches = [(p, b) for p, b in windows.modules(process.pid) if Path(p).name.lower() == "weixin.dll"]
        if not matches:
            raise ProbeError("ModuleNotLoaded")
        if len(matches) != 1:
            raise ProbeError("ModuleChanged")
        path, base = matches[0]
        cached = self.cached
        if cached and (cached.pid, cached.created, cached.path, cached.base, cached.file_id) == (
                process.pid, created, path, base, windows.file_identity(path)):
            return cached
        version, digest, machine, identity = windows.inspect_file(path)
        if windows.creation_time(process.pid) != created or (path, base) not in windows.modules(process.pid):
            raise ProbeError("ModuleChanged")
        profile, reason = match_profile(version, digest, machine)
        self.cached = Target(process.pid, created, path, base, version, digest, identity, profile, reason)
        return self.cached
