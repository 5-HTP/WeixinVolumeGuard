"""Create a Windows wheel lock from the exact downloaded build inputs."""
from pathlib import Path
import email
import hashlib
import zipfile

root=Path(__file__).resolve().parents[1]
rows=[]
for wheel in sorted((root/"artifacts/wheels").glob("*.whl")):
    with zipfile.ZipFile(wheel) as archive:
        name=next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        info=email.message_from_bytes(archive.read(name))
    with wheel.open("rb") as stream:
        digest=hashlib.file_digest(stream,"sha256").hexdigest()
    rows.append(f"{info['Name']}=={info['Version']} --hash=sha256:{digest}")
assert len(rows)==11
(root/"engine/requirements.lock.txt").write_text("\n".join(sorted(rows,key=str.lower))+"\n",encoding="utf-8")
print("Pinned",len(rows),"wheels with SHA-256")
