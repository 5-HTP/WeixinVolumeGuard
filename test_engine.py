import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import unittest
from unittest.mock import patch, Mock
import json
import queue
from dataclasses import replace
from guard_engine.profiles import KNOWN, match_profile
from guard_engine.__main__ import Controller
from guard_engine.process_probe import Target, ProbeError


class EngineTests(unittest.TestCase):
    def controller(self):
        with patch("guard_engine.__main__.ProcessProbe"), patch("guard_engine.__main__.AudioProbe"):
            c = Controller(lambda event: self.events.append(event))
        c.parent = 12
        c.parent_created = "1"
        c.target = Target(42,"2","module",0,"4.2.0.53","hash",(),KNOWN,None)
        c.next_scan = float("inf")
        c.desired = True
        return c

    def setUp(self):
        self.events = []
        self.alive = patch("guard_engine.__main__.psutil.pid_exists", return_value=True)
        self.created = patch("guard_engine.__main__.windows.creation_time", return_value="1")
        self.process = patch("guard_engine.__main__.psutil.Process")
        self.alive.start(); self.created.start(); self.process.start().return_value.children.return_value=[]
        self.addCleanup(self.alive.stop); self.addCleanup(self.created.stop); self.addCleanup(self.process.stop)

    def test_profiles_exact(self):
        self.assertEqual(match_profile(KNOWN.version,KNOWN.sha256,KNOWN.machine)[0],KNOWN)
        for version, digest, machine in [("4.2.0.54",KNOWN.sha256,KNOWN.machine),(KNOWN.version,"00",KNOWN.machine),(KNOWN.version,KNOWN.sha256,0xAA64)]:
            self.assertIsNone(match_profile(version,digest,machine)[0])

    def test_unknown_never_attaches(self):
        c=self.controller(); c.target=replace(c.target,profile=None,reason="UnknownDllHash")
        with patch("guard_engine.__main__.HookSession") as factory:
            c.tick(); factory.assert_not_called()
        self.assertEqual(c.state,"Unsupported")

    def test_stopped_still_scans(self):
        c=self.controller(); c.desired=False; c.next_scan=0; c.probe.scan.return_value=c.target
        with patch("guard_engine.__main__.HookSession") as factory:
            c.tick(); c.probe.scan.assert_called_once(); factory.assert_not_called()
        self.assertEqual(c.state,"Disabled")

    def test_capture_active_waits(self):
        c=self.controller(); c.audio.snapshot.return_value={"active":True,"outputCount":1}
        with patch("guard_engine.__main__.HookSession") as factory:
            c.tick(); factory.assert_not_called()
        self.assertEqual(c.state,"WaitingForRecordingIdle")

    def test_capture_error_does_not_attach(self):
        c=self.controller(); c.audio.snapshot.side_effect=ProbeError("AudioProbeFailed")
        with patch("guard_engine.__main__.HookSession") as factory:
            with self.assertRaises(ProbeError): c.tick()
            factory.assert_not_called()

    def test_cleanup_failure_is_not_disabled(self):
        c=self.controller(); c.hook=Mock(); c.hook.stats={}; c.hook.close.side_effect=RuntimeError("CleanupUnconfirmed")
        with self.assertRaises(RuntimeError): c.set_desired(False)
        self.assertTrue(c.cleanup_failed); self.assertEqual(c.state,"Error")

    def test_final_intent_generation(self):
        c=self.controller(); c.set_desired(False); c.set_desired(True); c.set_desired(False)
        self.assertEqual(c.generation,3); self.assertFalse(c.desired); self.assertEqual(c.state,"Disabled")

    def test_cleanup_retry_cannot_forge_confirmation(self):
        c=self.controller();c.target=replace(c.target,created="1");c.cleanup_failed=True;c.hook=None
        with self.assertRaises(RuntimeError):c.set_desired(False)
        self.assertTrue(c.cleanup_failed);self.assertEqual(c.state,"Error")

    def test_uncertain_cleanup_clears_only_after_process_exit(self):
        c=self.controller();c.cleanup_failed=True;c.hook=None;c.desired=False
        with patch("guard_engine.__main__.psutil.pid_exists",side_effect=lambda pid:pid==12):
            c.probe.scan.return_value=None;c.tick()
        self.assertFalse(c.cleanup_failed);self.assertEqual(c.state,"Disabled")

    def test_missing_process_waits(self):
        c=self.controller(); c.next_scan=0; c.probe.scan.return_value=None
        c.tick(); self.assertEqual(c.state,"WaitingForWeixin")


if __name__ == "__main__":
    unittest.main(verbosity=2)
