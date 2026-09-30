#!/usr/bin/python3
"""Forced SSH command: accept an archive or invoke the fixed deploy controller."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

CONFIG = Path("/etc/vezano-deploy.json")
CONTROLLER = "/usr/local/libexec/vezano/deploy_release.py"
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
SHA = r"[0-9a-f]{40}"
DIGEST = r"[0-9a-f]{64}"


def parse_command(command):
    if command == "ready":
        return ("ready",)
    match = re.fullmatch(rf"(upload|deploy) ({SHA}) ({DIGEST})", command)
    if not match:
        raise ValueError("command is not permitted")
    return match.groups()


def receive_archive(stream, incoming, sha, expected_digest, max_bytes=MAX_ARCHIVE_BYTES):
    digest = hashlib.sha256()
    total = 0
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=incoming, prefix=".upload-", delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("archive exceeds upload limit")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if not total or digest.hexdigest() != expected_digest:
            raise ValueError("archive checksum does not match")
        destination = Path(incoming) / f"{sha}.tar.gz"
        os.replace(temporary, destination)
        return total
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    os.umask(0o077)
    try:
        command = parse_command(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
        if command[0] == "ready":
            print("[deploy] SSH gateway ready")
            return 0
        _, sha, digest = command
        config = json.loads(CONFIG.read_text())
        if command[0] == "upload":
            size = receive_archive(sys.stdin.buffer, Path(config["incoming"]), sha, digest)
            print(f"[deploy] uploaded {size} bytes; checksum verified")
            return 0
        return subprocess.call(
            ["sudo", "-n", CONTROLLER, sha, digest],
            env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
    except (ValueError, OSError, KeyError):
        # Do not echo original commands, credentials or arbitrary subprocess output.
        print("[deploy] gateway rejected the request", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
