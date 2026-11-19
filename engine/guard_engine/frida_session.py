from pathlib import Path
import frida
from . import windows


class HookSession:
    def __init__(self, target, generation):
        self.session = None
        self.script = None
        self.stats = {}
        self.dead = False
        self.agent_error = None
        self.generation = generation
        try:
            if windows.creation_time(target.pid) != target.created or windows.file_identity(target.path) != target.file_id:
                raise RuntimeError("ModuleChanged")
            self.session = frida.get_local_device().attach(target.pid, persist_timeout=0)
            if self.session.persist_timeout != 0:
                raise RuntimeError("PersistentSessionRejected")
            self.session.on("detached", lambda *args: setattr(self, "dead", True))
            self.script = self.session.create_script(Path(__file__).with_name("resources").joinpath("agent.js").read_text(encoding="utf-8"))
            self.script.on("message", self.on_message)
            self.script.load()
            self.stats = self.script.exports_sync.setup(dict(
                generation=generation, moduleName="Weixin.dll", modulePath=target.path,
                moduleBase=hex(target.base), returnRva=target.profile.return_rva,
                systemDirectory=windows.system_directory()))
        except Exception:
            self.close()
            raise

    def on_message(self, message, data):
        if message.get("type") == "error":
            self.agent_error = message.get("description", "AgentError")

    def renew(self):
        if self.dead or self.agent_error:
            raise RuntimeError("AgentDisconnected")
        self.stats = self.script.exports_sync.renew(self.generation)
        if not self.stats.get("armed"):
            raise RuntimeError("AgentNotArmed")
        return self.stats

    def close(self):
        errors = []
        if self.script:
            try:
                if not self.dead:
                    self.script.exports_sync.cleanup()
            except Exception as exc:
                errors.append(str(exc))
            try:
                self.script.unload()
            except frida.InvalidOperationError:
                pass
            except Exception as exc:
                errors.append(str(exc))
            self.script = None
        if self.session:
            try:
                self.session.detach()
            except frida.InvalidOperationError:
                pass
            except Exception as exc:
                errors.append(str(exc))
            self.session = None
        if errors and not self.dead:
            raise RuntimeError("CleanupUnconfirmed")
