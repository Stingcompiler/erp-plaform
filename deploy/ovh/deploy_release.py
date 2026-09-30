#!/usr/bin/python3
"""Root-owned controller, callable only with a commit and archive checksum.

Never execute uploaded deployment scripts as root. Install reviewed controller
updates separately; the release itself runs as the application service user.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.request import Request, urlopen

CONFIG = Path("/etc/vezano-deploy.json")
UPGRADE = "/usr/local/libexec/vezano/upgrade.sh"
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 100000


def validate_arguments(sha, digest):
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid deployment identifier")


def safe_extract(archive_path, destination):
    """Accept regular files/directories only, without traversal or duplicate paths."""
    with tarfile.open(archive_path, "r:gz") as archive:
        members = []
        total = 0
        seen = set()
        for member in archive:
            if len(members) >= MAX_MEMBERS:
                raise ValueError("archive has too many members")
            members.append(member)
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe archive path")
            if not (member.isdir() or member.isfile()):
                raise ValueError("archive links/devices are not permitted")
            key = path.as_posix()
            if key in seen or (not path.parts and not member.isdir()):
                raise ValueError("duplicate or invalid archive entry")
            seen.add(key)
            if member.size < 0:
                raise ValueError("invalid archive size")
            total += member.size
            if total > MAX_EXPANDED_BYTES:
                raise ValueError("expanded archive exceeds limit")
        # Validation is complete before writing any member.
        for member in members:
            path = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
                path.chmod(0o755)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, path.open("xb") as target:
                    shutil.copyfileobj(source, target)
                path.chmod(0o644)


def copy_upload(incoming, sha, destination, expected_digest):
    """Open only a regular file in the fixed incoming directory, without following links."""
    directory = os.open(incoming, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(f"{sha}.tar.gz", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as source, destination.open("xb") as target:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("upload is not a regular file")
            digest = hashlib.sha256()
            total = 0
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > 512 * 1024 * 1024:
                    raise ValueError("archive exceeds limit")
                digest.update(chunk)
                target.write(chunk)
        if digest.hexdigest() != expected_digest:
            raise ValueError("copied archive checksum mismatch")
    finally:
        os.close(directory)


def require_latest_main(config, sha):
    # This repository is public: no GitHub token is sent to the production host.
    request = Request(
        f'https://api.github.com/repos/{config["repository"]}/commits/main',
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Vezano-deploy", "Cache-Control": "no-cache"},
    )
    with urlopen(request, timeout=15) as response:
        latest = json.load(response)["sha"]
    if latest != sha:
        raise ValueError("commit is no longer main HEAD; refusing stale deployment")


def app_command(config, arguments):
    return [
        "runuser", "-u", config["app_user"], "--", "env", "-i",
        "PATH=/usr/local/bin:/usr/bin:/bin", f'VEZANO_ENV_FILE={config["env_file"]}',
        *map(str, arguments),
    ]


def install_release(config, sha, digest, archive):
    releases = Path(config["releases"])
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=releases) as name:
        stage = Path(name)
        safe_extract(archive, stage)
        version = (stage / "VERSION").read_text().strip()
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.-]+)?", version):
            raise ValueError("invalid release version")
        for required in ("backend/manage.py", "backend/requirements.lock", "release-manifest.json", "frontend/out/index.html"):
            if not (stage / required).is_file():
                raise ValueError("archive lacks required release files")
        release = releases / f"{version}-{sha[:12]}-auto"
        metadata = {"commit": sha, "archive_sha256": digest}
        if release.exists():
            if json.loads((release / "DEPLOYMENT.json").read_text()) != metadata:
                raise ValueError("existing release belongs to a different artifact")
            return release
        account = pwd.getpwnam(config["app_user"])
        stage.chmod(0o700)
        for path in stage.rglob("*"):
            os.chown(path, account.pw_uid, account.pw_gid)
        (stage / "DEPLOYMENT.json").write_text(json.dumps(metadata) + "\n")
        os.chown(stage, account.pw_uid, account.pw_gid)
        stage.chmod(0o755)
        os.rename(stage, release)
        return release


def main():
    os.umask(0o077)
    log_path = None
    try:
        if os.geteuid() != 0 or len(sys.argv) != 3:
            raise ValueError("controller requires root and exactly two identifiers")
        sha, digest = sys.argv[1:]
        validate_arguments(sha, digest)
        config = json.loads(CONFIG.read_text())
        with open(config["lock"], "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            require_latest_main(config, sha)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            log_path = Path(config["logs"]) / f"{stamp}-{sha[:12]}.log"
            with log_path.open("x") as log:
                with tempfile.TemporaryDirectory(prefix="copy-", dir=config["private_stage"]) as name:
                    archive = Path(name) / "release.tar.gz"
                    copy_upload(config["incoming"], sha, archive, digest)
                    release = install_release(config, sha, digest, archive)
                if Path(config["link"]).resolve() == release.resolve():
                    print(f"[deploy] commit {sha[:12]} is already current")
                    return 0
                python = release / "venv/bin/python"
                if not python.is_file():
                    subprocess.run(app_command(config, [config["python"], "-m", "venv", release / "venv"]), check=True, stdout=log, stderr=log)
                # Retry incomplete dependency preparation against the same exact pins.
                subprocess.run(app_command(config, [python, "-m", "pip", "install", "--quiet", "-r", release / "backend/requirements.lock"]), check=True, stdout=log, stderr=log)
                mode = subprocess.run(
                    app_command(config, [python, release / "backend/manage.py", "shell", "--verbosity", "0", "-c", "from config.deployment import get_deployment_config; print(get_deployment_config().mode)"]),
                    check=True, stdout=subprocess.PIPE, stderr=log, text=True,
                ).stdout.strip()
                if mode != "saas":
                    raise ValueError("automatic OVH deployment requires SaaS mode")
                require_latest_main(config, sha)
                result = subprocess.run(
                    ["bash", UPGRADE, "--release", str(release), "--link", config["link"],
                     "--env-file", config["env_file"], "--backup-dir", config["backups"],
                     "--worker-service", "none", "--require-no-migrations", "--health-host", config["health_host"], "--yes"],
                    env={"PATH": "/usr/local/bin:/usr/bin:/bin"}, stdout=log, stderr=log,
                )
                if result.returncode:
                    print(f"[deploy] upgrade stopped; protected server log: {log_path}", file=sys.stderr)
                    return result.returncode
            # Do not stream Django/database output to publicly visible Actions logs.
            (Path(config["state"]) / "last-success.json").write_text(json.dumps({**metadata_for(sha, digest), "release": str(release), "completed_at": stamp}) + "\n")
            print(f"[deploy] healthy release promoted: {release.name}")
            print(f"[deploy] protected server log: {log_path}")
            return 0
    except Exception:
        # Detailed output stays on the protected host; never include secret-shaped errors.
        print("[deploy] request stopped before completion", file=sys.stderr)
        if log_path:
            print(f"[deploy] protected server log: {log_path}", file=sys.stderr)
        return 1


def metadata_for(sha, digest):
    return {"commit": sha, "archive_sha256": digest}


if __name__ == "__main__":
    sys.exit(main())
