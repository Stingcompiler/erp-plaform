#!/usr/bin/env node
// Cross-platform launcher for the Django dev server, used by
// .claude/launch.json. Finds the project's virtualenv interpreter (POSIX or
// Windows layout, `.venv` or `venv`), falling back to whatever Python is on
// PATH, then runs `manage.py runserver`. Node is always present because the
// frontend needs it, so this works on every contributor's machine.
const { spawnSync } = require("node:child_process");
const { existsSync } = require("node:fs");
const path = require("node:path");

const backend = path.resolve(__dirname, "..");
const isWindows = process.platform === "win32";
const candidates = [".venv", "venv"].map((dir) =>
  path.join(backend, dir, isWindows ? "Scripts\\python.exe" : "bin/python"),
);
const python =
  candidates.find((candidate) => existsSync(candidate)) ||
  (isWindows ? "python" : "python3");

const port = process.env.PORT || process.argv[2] || "8000";
const result = spawnSync(python, ["manage.py", "runserver", port], {
  cwd: backend,
  stdio: "inherit",
  env: { ...process.env, PYTHONUNBUFFERED: "1" },
});
if (result.error) {
  console.error(`Could not start ${python}: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
