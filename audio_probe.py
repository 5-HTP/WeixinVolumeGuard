import sys
sys.coinit_flags = 0

import time
import comtypes
from pycaw.pycaw import AudioUtilities, IAudioSessionControl2
from .process_probe import ProbeError


class AudioProbe:
    """Used exclusively by the controller's MTA thread; reads metadata only."""
    def __init__(self):
        self.devices = []
        self.refreshed = 0

    def snapshot(self, related_pids):
        if time.monotonic() - self.refreshed >= 2:
            self.devices = [d for d in AudioUtilities.GetAllDevices() if d.state.name == "Active"]
            self.refreshed = time.monotonic()
        outputs = [d for d in self.devices if d.id.startswith("{0.0.0.")]
        capture = [d for d in self.devices if d.id.startswith("{0.0.1.")]
        levels = {}
        active = False
        try:
            for device in outputs:
                levels[device.id] = float(device.EndpointVolume.GetMasterVolumeLevelScalar())
            for device in capture:
                sessions = device.AudioSessionManager.GetSessionEnumerator()
                for i in range(sessions.GetCount()):
                    control = sessions.GetSession(i).QueryInterface(IAudioSessionControl2)
                    if control.GetState() == 1 and control.GetProcessId() in related_pids:
                        active = True
            defaults = []
            enumerator = AudioUtilities.GetDeviceEnumerator()
            for role in range(3):
                try:
                    defaults.append(enumerator.GetDefaultAudioEndpoint(0, role).GetId())
                except comtypes.COMError:
                    defaults.append(None)
        except Exception as exc:
            self.refreshed = 0
            raise ProbeError("AudioProbeFailed") from exc
        return dict(active=active, levels=levels,
                    fingerprint=tuple(sorted(levels)) + tuple(defaults), outputCount=len(outputs))

    def close(self):
        self.devices.clear()
