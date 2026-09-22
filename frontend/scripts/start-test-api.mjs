import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const backend = fileURLToPath(new URL("../../backend/", import.meta.url));
const venvPython = fileURLToPath(
  new URL(
    process.platform === "win32"
      ? "../../backend/.venv/Scripts/python.exe"
      : "../../backend/.venv/bin/python",
    import.meta.url,
  ),
);
const python =
  process.env.PYTHON || (existsSync(venvPython) ? venvPython : "python");
const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8011"],
  {
    cwd: backend,
    stdio: "inherit",
    windowsHide: true,
    // Test isolation: never load developer credentials or make authenticated courier calls.
    env: {
      ...process.env,
      PYTHON_DOTENV_DISABLED: "1",
      AUSPOST_API_KEY: "",
      AUSPOST_API_PASSWORD: "",
      AUSPOST_ACCOUNT_NUMBER: "",
      STARTRACK_ACCOUNT_NUMBER: "",
    },
  },
);
child.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
