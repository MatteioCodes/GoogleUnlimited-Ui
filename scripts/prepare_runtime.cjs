const { spawnSync } = require("node:child_process");
const path = require("node:path");
const python =
  process.env.GOOGLE_UNLIMITED_PYTHON ||
  (process.platform === "win32" ? "python" : "python3");
const result = spawnSync(
  python,
  [path.join(__dirname, "prepare_runtime.py"), ...process.argv.slice(2)],
  { stdio: "inherit" },
);
if (result.error)
  console.error(
    "Building from source needs Python 3.11 or newer. Installed apps include their own Python runtime.",
  );
process.exit(result.status ?? 1);
