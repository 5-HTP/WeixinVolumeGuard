from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    id: str
    version: str
    sha256: str
    machine: int
    return_rva: int


KNOWN = Profile(
    "weixin-win-x64-4.2.0.53-ac6b174d", "4.2.0.53",
    "AC6B174D98EE1B69E95C99A7A39C3197C8C167B7C6D32F5B72C7A7659C104825",
    0x8664, 0x6DE6510,
)


def match_profile(version, sha256, machine):
    if machine != KNOWN.machine:
        return None, "UnsupportedArchitecture"
    if version != KNOWN.version:
        return None, "UnsupportedWeixinVersion"
    if sha256.upper() != KNOWN.sha256:
        return None, "UnknownDllHash"
    return KNOWN, None
