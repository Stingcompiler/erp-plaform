"""
Release packaging for standalone installs.

A customer release is a signed directory: application code, a pinned dependency
list, the built frontend, every migration, and this module's manifest. The
manifest records a SHA-256 for each part so an operator can prove that what they
unpacked is what the vendor built, and so an upgrade can refuse to run against a
tree that has been modified in transit.

Nothing here talks to a licence server or the network — a standalone install
must be installable and upgradeable offline from a hand-carried archive.
"""

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

MANIFEST_NAME = "release-manifest.json"
CHECKSUM_NAME = "SHA256SUMS"
HASH_CHUNK_BYTES = 1 << 20
REQUIREMENTS_RELATIVE = Path("backend") / "requirements.txt"
FRONTEND_OUT_RELATIVE = Path("frontend") / "out"


def repository_root():
    """The repository root, one level above the Django `backend/` package."""
    return Path(settings.BASE_DIR).resolve().parent


def application_version(root=None):
    """The released version, read from the root `VERSION` file."""
    version_file = (root or repository_root()) / "VERSION"
    if not version_file.is_file():
        return "0.0.0-unknown"
    return version_file.read_text(encoding="utf-8").strip() or "0.0.0-unknown"


def sha256_file(path, chunk_size=HASH_CHUNK_BYTES):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_tree(root, relative_to=None):
    """
    A single hash over every file under `root`, derived from the sorted list of
    `(relative path, file hash)` pairs. Paths are included so that renaming a
    file changes the digest even when its contents do not.
    """
    root = Path(root)
    base = Path(relative_to) if relative_to else root
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(base).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def iter_files(root):
    """Every regular file under `root`, in stable (sorted) path order."""
    root = Path(root)
    return sorted(path for path in root.rglob("*") if path.is_file())


def migration_inventory():
    """
    Every migration file shipped by every installed app, with its hash. Read
    from disk rather than the migration loader so that a file the loader would
    not yet apply (a future release's migration) is still covered.
    """
    from django.apps import apps

    rows = []
    for config in apps.get_app_configs():
        migrations_dir = Path(config.path) / "migrations"
        if not migrations_dir.is_dir():
            continue
        for path in sorted(migrations_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            rows.append(
                {
                    "app": config.label,
                    "name": path.name,
                    "sha256": sha256_file(path),
                }
            )
    rows.sort(key=lambda row: (row["app"], row["name"]))
    return rows


def dependency_inventory(requirements_path=None):
    """Pinned dependency lines and the hash of the requirements file itself."""
    path = Path(requirements_path or repository_root() / REQUIREMENTS_RELATIVE)
    if not path.is_file():
        return {"path": str(path), "present": False, "sha256": "", "packages": []}
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return {
        "path": str(path),
        "present": True,
        "sha256": sha256_file(path),
        "packages": lines,
    }


def frontend_inventory(frontend_out=None):
    """The built Next.js export: file count, size, tree hash, and index hash."""
    out_dir = Path(frontend_out or repository_root() / FRONTEND_OUT_RELATIVE)
    index = out_dir / "index.html"
    if not out_dir.is_dir():
        return {"present": False, "files": 0, "bytes": 0, "sha256": "", "index_sha256": ""}
    files = iter_files(out_dir)
    total_bytes = sum(path.stat().st_size for path in files)
    return {
        "present": True,
        "files": len(files),
        "bytes": total_bytes,
        "sha256": sha256_tree(out_dir),
        "index_sha256": sha256_file(index) if index.is_file() else "",
    }


def manifest_checksum(manifest):
    """
    A digest over the manifest's own content, excluding the checksum field it
    will be stored in. Detects any later edit to the manifest.
    """
    payload = {
        key: value for key, value in manifest.items() if key != "manifest_checksum"
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return sha256_bytes(canonical)


def build_manifest(root=None, requirements_path=None, frontend_out=None, extra=None):
    """Describe this tree: version, runtime, migrations, dependencies, frontend."""
    from django import get_version

    root = Path(root or repository_root())
    manifest = {
        "manifest_version": 1,
        "application_version": application_version(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "django_version": get_version(),
        "deployment_mode": settings.VEZANO_DEPLOYMENT_MODE,
        "migrations": migration_inventory(),
        "dependencies": dependency_inventory(requirements_path),
        "frontend": frontend_inventory(frontend_out),
    }
    if extra:
        manifest.update(extra)
    manifest["manifest_checksum"] = manifest_checksum(manifest)
    return manifest


def _migration_index(rows):
    return {(row["app"], row["name"]): row["sha256"] for row in rows}


def verify_manifest(manifest, root=None, requirements_path=None, frontend_out=None):
    """
    Compare a manifest against the tree on disk. Returns a list of plain-language
    problems; an empty list means the release matches what was signed. Callers
    decide whether a mismatch is fatal — an upgrade must treat it as fatal.
    """
    problems = []
    if not isinstance(manifest, dict):
        return ["The manifest is not a JSON object."]
    expected_checksum = manifest.get("manifest_checksum")
    if expected_checksum and expected_checksum != manifest_checksum(manifest):
        problems.append("The manifest checksum does not match its own contents.")

    root = Path(root or repository_root())
    version = manifest.get("application_version")
    if version and version != application_version(root):
        problems.append(
            f"Application version mismatch: manifest says {version}, "
            f"tree says {application_version(root)}."
        )

    expected = _migration_index(manifest.get("migrations") or [])
    actual = _migration_index(migration_inventory())
    for key in sorted(set(expected) - set(actual)):
        problems.append(f"Missing migration: {key[0]}/{key[1]}")
    for key in sorted(set(actual) - set(expected)):
        problems.append(f"Unexpected migration: {key[0]}/{key[1]}")
    for key in sorted(set(expected) & set(actual)):
        if expected[key] != actual[key]:
            problems.append(f"Modified migration: {key[0]}/{key[1]}")

    recorded_deps = (manifest.get("dependencies") or {}).get("sha256")
    current_deps = dependency_inventory(requirements_path)["sha256"]
    if recorded_deps and current_deps and recorded_deps != current_deps:
        problems.append("The dependency list has changed since the manifest was built.")

    recorded_frontend = (manifest.get("frontend") or {}).get("sha256")
    current_frontend = frontend_inventory(frontend_out)["sha256"]
    if recorded_frontend and current_frontend and recorded_frontend != current_frontend:
        problems.append("The built frontend does not match the manifest.")

    return problems


def write_manifest(manifest, destination):
    """Write the manifest as indented JSON and return the path written."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


def checksum_lines(manifest, root=None):
    """
    `sha256sum`-format lines for the parts an operator is most likely to
    re-verify by hand: the version, the dependency list, the frontend export and
    each requirement entry is covered by the dependency hash.
    """
    root = Path(root or repository_root())
    lines = []
    version_file = root / "VERSION"
    if version_file.is_file():
        lines.append(f"{sha256_file(version_file)}  VERSION")
    requirements = dependency_inventory(root / REQUIREMENTS_RELATIVE)
    if requirements["present"]:
        lines.append(f"{requirements['sha256']}  {REQUIREMENTS_RELATIVE.as_posix()}")
    frontend = manifest.get("frontend") or {}
    if frontend.get("sha256"):
        lines.append(f"{frontend['sha256']}  {FRONTEND_OUT_RELATIVE.as_posix()}")
    lines.append(f"{manifest['manifest_checksum']}  {MANIFEST_NAME}")
    return lines


def write_checksums(manifest, destination, root=None):
    """Write a SHA256SUMS file beside the manifest and return the path written."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(checksum_lines(manifest, root)) + "\n", encoding="utf-8")
    return destination
