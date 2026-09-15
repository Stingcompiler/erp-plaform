#!/usr/bin/env node
// Serves the production export against a throwaway SQLite database seeded
// with the E2E fixture (manage.py seed_e2e), for `npx playwright test` in
// frontend/. Used by .claude/launch.json ("e2e") and handy by hand:
//   node backend/scripts/e2e_server.js [port]
// The database lives in the OS temp dir and is recreated on every start, so
// a run never depends on — or touches — the developer's own db.sqlite3.
const { spawnSync, spawn } = require("node:child_process");
const { existsSync, rmSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const backend = path.resolve(__dirname, "..");
const isWindows = process.platform === "win32";
const python =
  [".venv", "venv"]
    .map((dir) => path.join(backend, dir, isWindows ? "Scripts\\python.exe" : "bin/python"))
    .find(existsSync) || (isWindows ? "python" : "python3");

const db = path.join(os.tmpdir(), "vezano-e2e.sqlite3");
rmSync(db, { force: true });
const env = {
  ...process.env,
  PYTHONUNBUFFERED: "1",
  DATABASE_URL: `sqlite:///${db}`,
  DEBUG: "True",
  DJANGO_SECRET_KEY: process.env.DJANGO_SECRET_KEY || "e2e-not-secret",
};
for (const args of [["manage.py", "migrate", "-v0"], ["manage.py", "seed_e2e"]]) {
  const r = spawnSync(python, args, { cwd: backend, stdio: "inherit", env });
  if (r.status !== 0) process.exit(r.status ?? 1);
}
const port = process.env.PORT || process.argv[2] || "8000";
const server = spawn(python, ["manage.py", "runserver", port, "--noreload"], { cwd: backend, stdio: "inherit", env });
server.on("exit", (code) => process.exit(code ?? 1));
