#!/usr/bin/env python3
"""
Offline repo structure audit (M12).

Verifies, without importing Django:
  1. every local app with a urls.py is wired into config/urls.py, and
  2. the migration dependency graph has no dangling local references.

Run from the backend/ directory: `python scripts/repo_audit.py`.
Exits non-zero on any problem so CI fails fast.
"""

import ast
import glob
import os
import re
import sys

LOCAL_APPS = {
    "core", "accounts", "org", "inventory", "sales", "purchasing",
    "returns", "sync", "website", "reports", "ops", "tax",
}


def load_installed_local_apps():
    settings = open("config/settings.py").read()
    block = re.search(r"INSTALLED_APPS = \[(.*?)\]", settings, re.S).group(1)
    return [a for a in re.findall(r'"([a-z_]+)"', block) if a in LOCAL_APPS]


def check_url_wiring(apps):
    root = open("config/urls.py").read()
    missing = [
        app for app in apps
        if os.path.exists(f"{app}/urls.py")
        and f'include("{app}.urls")' not in root
    ]
    return missing


def _dependencies(path):
    tree = ast.parse(open(path).read())
    deps = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", None) == "dependencies" for t in node.targets
        ):
            for el in ast.walk(node.value):
                if isinstance(el, ast.Tuple) and len(el.elts) == 2:
                    try:
                        a, b = el.elts[0].value, el.elts[1].value
                        if isinstance(a, str) and isinstance(b, str):
                            deps.append((a, b))
                    except AttributeError:
                        pass
    return deps


def check_migration_graph(apps):
    files = glob.glob("*/migrations/0*.py")
    nodes = {
        (f.split("/")[0], os.path.basename(f)[:-3]) for f in files
    }
    problems = []
    for f in files:
        node = (f.split("/")[0], os.path.basename(f)[:-3])
        for dep in _dependencies(f):
            if dep[0] in apps and dep not in nodes:
                problems.append((node, dep))
    return problems, len(nodes)


def main():
    apps = load_installed_local_apps()
    ok = True

    missing = check_url_wiring(apps)
    if missing:
        ok = False
        print(f"FAIL: apps with urls.py not wired: {missing}")
    else:
        print(f"OK: URL wiring ({len(apps)} local apps)")

    problems, count = check_migration_graph(apps)
    if problems:
        ok = False
        print(f"FAIL: broken migration dependencies: {problems}")
    else:
        print(f"OK: migration graph ({count} migrations)")

    # No Docker anywhere.
    docker = glob.glob("../**/Dockerfile*", recursive=True) + glob.glob(
        "../**/docker-compose*", recursive=True
    )
    docker = [d for d in docker if "node_modules" not in d]
    if docker:
        ok = False
        print(f"FAIL: Docker artifacts present: {docker}")
    else:
        print("OK: no Docker artifacts")

    print("AUDIT PASSED" if ok else "AUDIT FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
