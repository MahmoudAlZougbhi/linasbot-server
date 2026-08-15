#!/usr/bin/env python3
"""Bounded SSH streaming and authenticated control-plane bootstrap for node02."""

from __future__ import annotations

import json
import os
import selectors
import shlex
import subprocess
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import BinaryIO, Final, cast

from scripts.ha import python_runtime_archive_contract as archive
from scripts.ha import python_runtime_provision_contract as contract
from scripts.ha import python_runtime_provision_state as state
from scripts.ha import release_artifact_contract as release

PEER_HOST: Final = "10.106.0.4"
SSH_BIN = "/usr/bin/ssh"
SSH_OPTIONS: Final = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=8",
    "-o",
    "ServerAliveInterval=5",
    "-o",
    "ServerAliveCountMax=3",
    "-o",
    "StrictHostKeyChecking=yes",
)
REMOTE_STAGE = r"""
import fcntl,hashlib,json,os,posixpath,stat,sys,tarfile,tempfile
from pathlib import Path,PurePosixPath
tx,plan_sha,plan_size,manifest_sha,manifest_size,control_sha,control_size,wheel_sha,wheel_size,dashboard_sha,dashboard_size,source_sha,source_size,runtime_name,runtime_sha,runtime_size=sys.argv[1:]
if not __import__("re").fullmatch(r"pyr_[0-9a-f]{32}",tx): raise SystemExit("bad transaction")
if any(not __import__("re").fullmatch(r"[0-9a-f]{64}",x) for x in (plan_sha,manifest_sha,control_sha,wheel_sha,dashboard_sha,source_sha,runtime_sha)): raise SystemExit("bad digest")
sizes=[int(plan_size),int(manifest_size),int(control_size),int(wheel_size),int(dashboard_size),int(source_size),int(runtime_size)]
if not (1<=sizes[0]<=1048576 and 1<=sizes[1]<=1048576 and 1<=sizes[2]<=268435456 and 1<=sizes[3]<=1073741824 and 1<=sizes[4]<=1073741824 and 1<=sizes[5]<=1073741824 and 1<=sizes[6]<=268435456): raise SystemExit("bad size")
root=Path("/var/lib/linasbot/meta-ha"); lock=Path("/run/lock/linasbot-meta-live.lock")
def secure_dir(path,mode,create=False):
 if create: path.mkdir(parents=True,exist_ok=True,mode=mode); os.chmod(path,mode); os.chown(path,0,0)
 s=path.lstat()
 if not stat.S_ISDIR(s.st_mode) or stat.S_ISLNK(s.st_mode) or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(0,0,mode): raise SystemExit("unsafe directory")
def syncdir(path):
 fd=os.open(path,os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0)); os.fsync(fd); os.close(fd)
def canonical(value): return (json.dumps(value,allow_nan=False,separators=(",",":"),sort_keys=True)+"\n").encode()
def read_safe(path,limit,mode=0o600):
 s=path.lstat()
 if not stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode) or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),s.st_nlink)!=(0,0,mode,1) or not 1<=s.st_size<=limit: raise SystemExit("unsafe file")
 fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)); opened=os.fstat(fd); chunks=[]; consumed=0
 if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)!=(opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns): raise SystemExit("file changed")
 while consumed<s.st_size:
  chunk=os.read(fd,min(1048576,s.st_size-consumed))
  if not chunk: raise SystemExit("short file")
  chunks.append(chunk); consumed+=len(chunk)
 if os.read(fd,1): raise SystemExit("long file")
 after=os.fstat(fd); os.close(fd)
 if (opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns): raise SystemExit("file changed")
 data=b"".join(chunks)
 return data
def writeall(fd,payload):
 view=memoryview(payload)
 while view:
  written=os.write(fd,view)
  if written<1: raise SystemExit("short write")
  view=view[written:]
def partial_unlink(path):
 s=path.lstat()
 if not stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode) or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),s.st_nlink)!=(0,0,0o600,1): raise SystemExit("unsafe partial file")
 path.unlink(); syncdir(path.parent)
def adopt(path,tmp,size):
 if not (os.path.lexists(path) and os.path.lexists(tmp)): return
 a=path.lstat(); b=tmp.lstat()
 if (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino) and stat.S_ISREG(a.st_mode) and not stat.S_ISLNK(a.st_mode) and (a.st_uid,a.st_gid,stat.S_IMODE(a.st_mode),a.st_nlink,a.st_size)==(0,0,0o600,2,size):
  tmp.unlink(); syncdir(path.parent)
def link_publish(path,tmp,digest,size,limit):
 adopt(path,tmp,size)
 if os.path.lexists(path):
  data=read_safe(path,limit)
  if len(data)!=size or hashlib.sha256(data).hexdigest()!=digest: raise SystemExit("published file conflict")
  if os.path.lexists(tmp): partial_unlink(tmp)
  return
 try: os.link(tmp,path,follow_symlinks=False)
 except FileExistsError: raise SystemExit("publication collision")
 syncdir(path.parent); tmp.unlink(); syncdir(path.parent)
def receive(path,size,digest):
 tmp=path.parent/("."+path.name+".receiving"); adopt(path,tmp,size)
 if os.path.lexists(tmp): partial_unlink(tmp)
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600); h=hashlib.sha256(); left=size
 try:
  os.fchmod(fd,0o600); os.fchown(fd,0,0)
  while left:
   chunk=sys.stdin.buffer.read(min(left,1048576))
   if not chunk: raise SystemExit("short stream")
   writeall(fd,chunk); h.update(chunk); left-=len(chunk)
  os.fsync(fd); os.close(fd); fd=-1
  if h.hexdigest()!=digest: raise SystemExit("stream digest mismatch")
  syncdir(path.parent); link_publish(path,tmp,digest,size,size)
 finally:
  if fd>=0: os.close(fd)
  try: partial_unlink(tmp)
  except FileNotFoundError: pass
def publish(path,data):
 tmp=path.parent/("."+path.name+".writing"); digest=hashlib.sha256(data).hexdigest(); adopt(path,tmp,len(data))
 if os.path.lexists(path):
  if read_safe(path,8388608)!=data: raise SystemExit("control module conflict")
  if os.path.lexists(tmp): partial_unlink(tmp)
  return
 if os.path.lexists(tmp): partial_unlink(tmp)
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
 try:
  os.fchmod(fd,0o600); os.fchown(fd,0,0); writeall(fd,data); os.fsync(fd); os.close(fd); fd=-1
  syncdir(path.parent); link_publish(path,tmp,digest,len(data),8388608)
 finally:
  if fd>=0: os.close(fd)
  try: partial_unlink(tmp)
  except FileNotFoundError: pass
lock.parent.mkdir(parents=True,exist_ok=True)
lfd=os.open(lock,os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0),0o600); os.fchmod(lfd,0o600); os.fchown(lfd,0,0); fcntl.flock(lfd,fcntl.LOCK_EX)
secure_dir(root,0o700,True)
for rel in ("bootstrap.active","bootstrap.coordinator.json","transaction.json","env.before","deploy.active","deploy-node.active","controlled-failover.active","registry-nfs-retire.active","rekey/runtime.guard"):
 if os.path.lexists(root/rel): raise SystemExit("collision: "+rel)
txroot=root/"python-runtime-transactions"/tx; secure_dir(root/"python-runtime-transactions",0o700,True); secure_dir(txroot,0o700,True)
active=root/"python-runtime-provision.active"; expected={"schema":1,"format":"linas-python-runtime-active-v1","transaction_id":tx,"node_id":"node02","plan_sha256":plan_sha}
publish(active,canonical(expected))
authority=txroot/"authority"; secure_dir(authority,0o700,True)
plan=authority/"plan.json"; manifest=authority/"release-manifest.json"; control=authority/"control-plane.tar"; wheel=authority/"wheelhouse.tar"; dashboard=authority/"dashboard-build.tar"; source_bundle=authority/"source.bundle"; runtime=authority/runtime_name
receive(plan,sizes[0],plan_sha); receive(manifest,sizes[1],manifest_sha); receive(control,sizes[2],control_sha); receive(wheel,sizes[3],wheel_sha); receive(dashboard,sizes[4],dashboard_sha); receive(source_bundle,sizes[5],source_sha); receive(runtime,sizes[6],runtime_sha)
if sys.stdin.buffer.read(1): raise SystemExit("oversized stream")
plan_raw=read_safe(plan,1048576); raw=read_safe(manifest,1048576)
def pairs(values):
 out={}
 for k,v in values:
  if k in out: raise SystemExit("duplicate JSON")
  out[k]=v
 return out
q=json.loads(plan_raw,object_pairs_hook=pairs); m=json.loads(raw,object_pairs_hook=pairs)
if canonical(q)!=plan_raw or hashlib.sha256(plan_raw).hexdigest()!=plan_sha or q.get("transaction_id")!=tx: raise SystemExit("bad plan")
if canonical(m)!=raw or m.get("schema")!="linasbot-release-manifest-v1" or hashlib.sha256(raw).hexdigest()!=manifest_sha: raise SystemExit("bad manifest")
p=m.get("payloads",{}); cp=p.get("control_plane",{}); wh=p.get("wheelhouse",{}); ds=p.get("dashboard",{}); sb=p.get("source_bundle",{}); pr=p.get("python_runtime",{})
if set(cp)!={"archive","archive_sha256","tree_sha256","file_count","total_size"} or cp.get("archive")!="control-plane.tar" or cp.get("archive_sha256")!=control_sha or wh.get("archive")!="wheelhouse.tar" or wh.get("archive_sha256")!=wheel_sha or ds.get("archive")!="dashboard-build.tar" or ds.get("archive_sha256")!=dashboard_sha or sb.get("file")!="source.bundle" or sb.get("sha256")!=source_sha or sb.get("size")!=sizes[5] or pr!={"file":runtime_name,"sha256":runtime_sha,"size":sizes[6]}: raise SystemExit("mixed authority")
if q.get("qg_manifest_sha256")!=manifest_sha or q.get("qg_run_id")!=m.get("run_id") or q.get("qg_run_attempt")!=m.get("run_attempt") or q.get("qg_target_sha")!=m.get("target_sha"): raise SystemExit("mixed plan identity")
expected=set(__CONTROL_MEMBERS_JSON__); domain=b"linasbot-release-tree-v1\0"
def record(digest,kind,name,mode,size,content): digest.update(json.dumps([kind,name,mode,size,content],separators=(",",":")).encode()+b"\n")
def control_tree(path):
 secure_dir(path,0o700); entries=[]
 for item in path.rglob("*"):
  name=item.relative_to(path).as_posix(); info=item.lstat()
  if name not in expected or info.st_uid!=0 or info.st_gid!=0 or stat.S_ISLNK(info.st_mode): raise SystemExit("unsafe control tree")
  entries.append((name,item,info))
 if {x[0] for x in entries}!=expected: raise SystemExit("incomplete control tree")
 digest=hashlib.sha256(domain); count=total=0
 for name,item,info in sorted(entries,key=lambda x:x[0].encode()):
  if stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o755: record(digest,"dir",name,0o755,0,None)
  elif stat.S_ISREG(info.st_mode) and info.st_nlink==1 and stat.S_IMODE(info.st_mode) in (0o644,0o755):
   data=read_safe(item,8388608,stat.S_IMODE(info.st_mode)); record(digest,"file",name,stat.S_IMODE(info.st_mode),len(data),hashlib.sha256(data).hexdigest()); count+=1; total+=len(data)
  else: raise SystemExit("bad control tree object")
 return digest.hexdigest(),count,total
def quarantine(path,label):
 secure_dir(path,0o700); prefix=".quarantine-"+label+"-"; numbers=sorted(int(x.name.removeprefix(prefix)) for x in path.parent.iterdir() if x.name.startswith(prefix) and x.name.removeprefix(prefix).isdigit())
 if numbers!=list(range(1,len(numbers)+1)): raise SystemExit("bad control quarantine sequence")
 os.rename(path,path.parent/(prefix+f"{len(numbers)+1:06d}")); syncdir(path.parent)
controlroot=txroot/"control"; extracting=txroot/".control.extracting"; wanted=(cp.get("tree_sha256"),cp.get("file_count"),cp.get("total_size"))
if os.path.lexists(controlroot):
 try: existing=control_tree(controlroot)
 except SystemExit: quarantine(controlroot,"control")
 else:
  if existing!=wanted: quarantine(controlroot,"control")
if not os.path.lexists(controlroot):
 if os.path.lexists(extracting): quarantine(extracting,"control-incomplete")
 secure_dir(extracting,0o700,True); tree=hashlib.sha256(domain); seen=set(); count=total=0; previous=None
 with tarfile.open(control,"r:") as tf:
  for member in tf:
   name=member.name; parts=name.split("/"); ordering=name.encode()
   if not name or name.startswith("/") or "\\" in name or any(x in ("",".","..") for x in parts) or str(PurePosixPath(name))!=name or name in seen or name not in expected or (previous is not None and ordering<=previous): raise SystemExit("unsafe control archive")
   previous=ordering; parent=str(PurePosixPath(name).parent)
   if parent!="." and parent not in seen: raise SystemExit("missing control parent")
   if set(member.pax_headers)-{"path"} or ("path" in member.pax_headers and member.pax_headers["path"]!=name) or (member.uid,member.gid,member.uname,member.gname,member.mtime)!=(0,0,"","",0): raise SystemExit("bad control metadata")
   target=extracting.joinpath(*parts)
   if member.isdir() and member.mode==0o755 and member.size==0:
    target.mkdir(mode=0o755); os.chown(target,0,0); os.chmod(target,0o755); record(tree,"dir",name,0o755,0,None)
   elif member.isfile() and member.mode in (0o644,0o755) and 0<member.size<=8388608:
    source=tf.extractfile(member); data=source.read(8388609) if source else b""
    if len(data)!=member.size: raise SystemExit("bad control member")
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),member.mode); os.fchmod(fd,member.mode); os.fchown(fd,0,0); writeall(fd,data); os.fsync(fd); os.close(fd)
    record(tree,"file",name,member.mode,len(data),hashlib.sha256(data).hexdigest()); count+=1; total+=len(data)
   else: raise SystemExit("bad control object")
   seen.add(name)
 if seen!=expected or (tree.hexdigest(),count,total)!=wanted: raise SystemExit("control tree mismatch")
 for item in sorted((x for x in extracting.rglob("*") if x.is_dir()),key=lambda x:len(x.parts),reverse=True): syncdir(item)
 syncdir(extracting); os.rename(extracting,controlroot); syncdir(txroot)
if control_tree(controlroot)!=wanted: raise SystemExit("control tree readback mismatch")
sys.path.insert(0,str(controlroot))
from scripts.ha.python_runtime_provision_ingest import _install
if _install(authority,0,q.get("qg_artifact_id"),q.get("qg_artifact_api_sha256"),manifest_sha,q.get("qg_run_id"),q.get("qg_run_attempt"),q.get("qg_target_sha"),retained_transaction_id=tx,emit_ack=False): raise SystemExit("peer ingest failed")
print(json.dumps({"schema":1,"status":"staged","transaction_id":tx,"plan_sha256":plan_sha},separators=(",",":"),sort_keys=True))
"""

REMOTE_STAGE = REMOTE_STAGE.replace(
    "__CONTROL_MEMBERS_JSON__",
    json.dumps(sorted(release.CONTROL_PLANE_MEMBERS), separators=(",", ":")),
)


def _ssh_command(*remote: str) -> list[str]:
    remote_argv = [
        "/usr/bin/env",
        "-i",
        "HOME=/root",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        "/usr/bin/python3",
        "-B",
        "-I",
        "-S",
        *remote,
    ]
    return [
        SSH_BIN,
        *SSH_OPTIONS,
        f"root@{PEER_HOST}",
        shlex.join(remote_argv),
    ]


def _payload_chunks(
    plan_raw: bytes,
    files: tuple[Path, ...],
    evidence: tuple[tuple[str, int], ...],
) -> Iterator[bytes]:
    yield plan_raw
    for path, (_expected, limit) in zip(files, evidence, strict=True):
        with archive.open_regular(path, max_bytes=limit) as (handle, _before):
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk


def _bounded_pump(command: list[str], chunks: Iterable[bytes], *, timeout: int) -> tuple[int, bytes, bytes]:
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    streams = (process.stdin, process.stdout, process.stderr)
    for stream in streams:
        os.set_blocking(stream.fileno(), False)
    selector = selectors.DefaultSelector()
    selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    iterator = iter(chunks)
    current = memoryview(b"")
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("peer stream exceeded its fixed deadline")
            events = selector.select(min(remaining, 1.0))
            if not events and process.poll() is not None:
                for key in list(selector.get_map().values()):
                    if key.data == "stdin":
                        selector.unregister(key.fileobj)
                        cast(BinaryIO, key.fileobj).close()
                        process.stdin = None
                continue
            for key, _mask in events:
                stream = cast(BinaryIO, key.fileobj)
                if key.data == "stdin":
                    try:
                        if not current:
                            current = memoryview(next(iterator))
                        written = os.write(stream.fileno(), current[:65536])
                        current = current[written:]
                    except StopIteration:
                        selector.unregister(stream)
                        stream.close()
                        process.stdin = None
                    except BrokenPipeError:
                        selector.unregister(stream)
                        stream.close()
                        process.stdin = None
                else:
                    try:
                        data = os.read(stream.fileno(), 65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        selector.unregister(stream)
                        stream.close()
                    else:
                        channel = str(key.data)
                        if channel not in output:
                            raise archive.ProvisionError("peer selector channel is invalid")
                        output[channel].extend(data)
                        if len(output[channel]) > 1024 * 1024:
                            raise archive.ProvisionError("peer process output exceeds its bound")
        return (
            process.wait(timeout=max(1.0, deadline - time.monotonic())),
            bytes(output["stdout"]),
            bytes(output["stderr"]),
        )
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            close()
        selector.close()


def stage_peer(paths: state.ProvisionPaths, plan: dict[str, object], plan_sha256: str) -> Path:
    tx_id = str(plan["transaction_id"])
    authority = paths.tx_root(tx_id) / "authority"
    manifest = authority / "release-manifest.json"
    control = authority / "control-plane.tar"
    wheelhouse = authority / "wheelhouse.tar"
    dashboard = authority / "dashboard-build.tar"
    source_bundle = authority / "source.bundle"
    runtime = authority / str(plan["artifact_name"])
    plan_raw = contract.canonical(plan)
    try:
        manifest_payload = release.load_manifest(
            manifest,
            expected_repository=str(plan["qg_repository"]),
            expected_workflow_ref=str(plan["qg_workflow_ref"]),
            expected_run_id=plan["qg_run_id"],
            expected_run_attempt=plan["qg_run_attempt"],
            expected_target_sha=str(plan["qg_target_sha"]),
        )
    except release.ContractError as exc:
        raise archive.ProvisionError("peer manifest snapshot is invalid") from exc
    files = (manifest, control, wheelhouse, dashboard, source_bundle, runtime)
    evidence = (
        (str(plan["qg_manifest_sha256"]), 1024 * 1024),
        (str(plan["control_plane_archive_sha256"]), archive.MAX_ARCHIVE_BYTES),
        (str(plan["wheelhouse_archive_sha256"]), 1024**3),
        (str(manifest_payload["payloads"]["dashboard"]["archive_sha256"]), 1024**3),
        (str(manifest_payload["payloads"]["source_bundle"]["sha256"]), 1024**3),
        (str(plan["artifact_sha256"]), archive.MAX_ARCHIVE_BYTES),
    )
    sizes: list[int] = []
    for path, (expected_sha, limit) in zip(files, evidence, strict=True):
        digest, size = archive.file_evidence(path, max_bytes=limit)
        if digest != expected_sha:
            raise archive.ProvisionError("peer stream authority differs from the durable snapshot")
        sizes.append(size)
    command = _ssh_command(
        "-c",
        REMOTE_STAGE,
        tx_id,
        plan_sha256,
        str(len(plan_raw)),
        str(plan["qg_manifest_sha256"]),
        str(sizes[0]),
        str(plan["control_plane_archive_sha256"]),
        str(sizes[1]),
        str(plan["wheelhouse_archive_sha256"]),
        str(sizes[2]),
        str(manifest_payload["payloads"]["dashboard"]["archive_sha256"]),
        str(sizes[3]),
        str(manifest_payload["payloads"]["source_bundle"]["sha256"]),
        str(sizes[4]),
        str(plan["artifact_name"]),
        str(plan["artifact_sha256"]),
        str(sizes[5]),
    )
    returncode, stdout, stderr = _bounded_pump(command, _payload_chunks(plan_raw, files, evidence), timeout=600)
    if returncode:
        raise archive.ProvisionError(f"peer authority staging failed: {stderr.decode('utf-8', 'replace')[:400]}")
    expected_ack = {
        "schema": 1,
        "status": "staged",
        "transaction_id": tx_id,
        "plan_sha256": plan_sha256,
    }
    try:
        observed = json.loads(stdout.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise archive.ProvisionError("peer staging acknowledgement is invalid") from exc
    if observed != expected_ack:
        raise archive.ProvisionError("peer staging acknowledgement does not bind the plan")
    return Path("/var/lib/linasbot/meta-ha") / state.TRANSACTIONS_NAME / tx_id / "control"


def call_peer(
    control_root: Path,
    arguments: list[str],
    *,
    input_payload: bytes | None = None,
    timeout: int = 600,
) -> dict[str, object]:
    expected_prefix = Path("/var/lib/linasbot/meta-ha") / state.TRANSACTIONS_NAME
    try:
        control_root.relative_to(expected_prefix)
    except ValueError as exc:
        raise archive.ProvisionError("peer control root is outside the transaction namespace") from exc
    wrapper = (
        "import sys;root=sys.argv.pop(1);sys.path.insert(0,root);"
        "from scripts.ha.provision_python_runtime_ha import main;raise SystemExit(main(sys.argv[1:]))"
    )
    result = subprocess.run(
        _ssh_command("-c", wrapper, str(control_root), *arguments),
        input=input_payload,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode:
        raise archive.ProvisionError(f"peer runtime operation failed: {result.stderr.decode('utf-8', 'replace')[:400]}")
    try:
        payload = json.loads(result.stdout.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise archive.ProvisionError("peer runtime acknowledgement is invalid") from exc
    if not isinstance(payload, dict):
        raise archive.ProvisionError("peer runtime acknowledgement schema is invalid")
    return payload
