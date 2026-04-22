"""Manage the codex-proxy backend lifecycle.

Two responsibilities:
  1. install()        — first-time clone + npm install + build (~5 min)
  2. ensure_running() — fast spawn-if-not-running + health check (called per session)

State lives under ~/.red-team-mcp/ (override with RED_TEAM_MCP_HOME):
  codex-proxy/        — the cloned source tree
  codex-proxy.pid     — last spawned PID
  codex-proxy.log     — captured stdout/stderr
  proxy.key           — auto-generated bearer token (read by codex_proxy.py)

Idempotent: every method may be called any number of times. Cross-platform
(Windows / macOS / Linux / WSL). Designed so MCP clients can spawn this
process repeatedly without compounding state.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

CODEX_PROXY_REPO = "https://github.com/icebear0828/codex-proxy.git"
DEFAULT_PORT = 8080
HEALTH_TIMEOUT_SECONDS = 60
NPM_TIMEOUT_SECONDS = 600
GIT_TIMEOUT_SECONDS = 180


def _default_home() -> Path:
    return Path(os.environ.get("RED_TEAM_MCP_HOME", str(Path.home() / ".red-team-mcp")))


def _is_windows() -> bool:
    return sys.platform == "win32"


def _missing_prereqs() -> list[str]:
    return [c for c in ("git", "node", "npm") if shutil.which(c) is None]


@dataclass
class Lifecycle:
    home: Path
    port: int = DEFAULT_PORT

    @property
    def proxy_dir(self) -> Path:
        return self.home / "codex-proxy"

    @property
    def pidfile(self) -> Path:
        return self.home / "codex-proxy.pid"

    @property
    def logfile(self) -> Path:
        return self.home / "codex-proxy.log"

    @property
    def keyfile(self) -> Path:
        return self.home / "proxy.key"

    # --- predicates -------------------------------------------------------

    def is_installed(self) -> bool:
        return (
            (self.proxy_dir / "package.json").exists()
            and (self.proxy_dir / "node_modules").exists()
            and (self.proxy_dir / "public" / "index.html").exists()
        )

    def is_port_listening(self) -> bool:
        try:
            r = httpx.get(f"http://localhost:{self.port}/", timeout=2.0)
            return r.status_code < 500
        except httpx.HTTPError:
            return False

    # --- install ----------------------------------------------------------

    def install(self) -> tuple[bool, str | None]:
        """Clone codex-proxy + npm install + build:web. Blocking, slow on first
        run (~5 min). Idempotent: existing clones are reused, npm is content-
        addressable so re-runs are fast.

        Also seeds data/local.yaml with a freshly generated proxy_api_key
        bound to localhost only, and writes that key to ~/.red-team-mcp/proxy.key
        so the MCP server can pick it up without the user pasting it."""
        missing = _missing_prereqs()
        if missing:
            return False, _prereq_error(missing)

        self.home.mkdir(parents=True, exist_ok=True)

        if not self.proxy_dir.exists():
            r = subprocess.run(
                ["git", "clone", "--depth=1", CODEX_PROXY_REPO, str(self.proxy_dir)],
                capture_output=True,
                text=True,
                timeout=GIT_TIMEOUT_SECONDS,
            )
            if r.returncode != 0:
                return False, f"[red-team-mcp] git clone failed:\n{r.stderr.strip()}"

        for stage in (
            ("npm install (root)",   ["npm", "install"], self.proxy_dir,         NPM_TIMEOUT_SECONDS),
            ("npm install (web)",    ["npm", "install"], self.proxy_dir / "web", NPM_TIMEOUT_SECONDS),
            ("npm run build:web",    ["npm", "run", "build:web"], self.proxy_dir, GIT_TIMEOUT_SECONDS),
        ):
            label, cmd, cwd, timeout = stage
            r = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True,
                timeout=timeout, shell=_is_windows(),
            )
            if r.returncode != 0:
                tail = (r.stderr or r.stdout).strip()[-800:]
                return False, f"[red-team-mcp] {label} failed:\n{tail}"

        self._seed_local_config()
        return True, None

    def _seed_local_config(self) -> None:
        """Write data/local.yaml with a fresh API key + localhost-only binding.
        Skips if a non-empty config already exists, so user edits are preserved."""
        cfg_path = self.proxy_dir / "data" / "local.yaml"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)

        if cfg_path.exists() and cfg_path.read_text().strip():
            # Respect existing config; just publish the existing key if we can find it.
            existing = cfg_path.read_text()
            for line in existing.splitlines():
                line = line.strip()
                if line.startswith("proxy_api_key:"):
                    self.keyfile.write_text(line.split(":", 1)[1].strip().strip("\"'"))
                    return

        key = secrets.token_urlsafe(24)
        cfg_path.write_text(
            f"server:\n"
            f"  proxy_api_key: {key}\n"
            f'  host: "127.0.0.1"\n'
        )
        self.keyfile.write_text(key)

    # --- run / stop -------------------------------------------------------

    def spawn_detached(self) -> tuple[bool, str | None]:
        """Start codex-proxy as a detached background process. Returns immediately;
        caller should follow with wait_for_health()."""
        try:
            log = open(self.logfile, "ab")
        except OSError as exc:
            return False, f"[red-team-mcp] cannot open log file {self.logfile}: {exc}"

        try:
            if _is_windows():
                DETACHED_PROCESS = 0x00000008
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                proc = subprocess.Popen(
                    ["npm", "run", "dev"],
                    cwd=str(self.proxy_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                    shell=True,
                )
            else:
                proc = subprocess.Popen(
                    ["npm", "run", "dev"],
                    cwd=str(self.proxy_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except FileNotFoundError as exc:
            return False, f"[red-team-mcp] failed to spawn codex-proxy: {exc}"

        self.pidfile.write_text(str(proc.pid))
        return True, None

    def wait_for_health(self, timeout: int = HEALTH_TIMEOUT_SECONDS) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_port_listening():
                return True
            time.sleep(1.0)
        return False

    # --- top-level entry points ------------------------------------------

    def ensure_running(self) -> tuple[bool, str | None]:
        """Fast-path used by the MCP server on every cold start. Does NOT install."""
        if self.is_port_listening():
            return True, None
        if not self.is_installed():
            return False, (
                "[red-team-mcp] codex-proxy is not installed. Run one-time setup:\n"
                "    uvx red-team-mcp install\n"
                "or set CODEX_PROXY_URL to an already-running OpenAI-compatible endpoint."
            )
        ok, err = self.spawn_detached()
        if not ok:
            return False, err
        if not self.wait_for_health():
            return False, (
                f"[red-team-mcp] codex-proxy was spawned but did not become healthy "
                f"within {HEALTH_TIMEOUT_SECONDS}s. See log: {self.logfile}"
            )
        return True, None


def get_lifecycle() -> Lifecycle:
    return Lifecycle(home=_default_home())


def _prereq_error(missing: list[str]) -> str:
    urls = {
        "git": "https://git-scm.com/",
        "node": "https://nodejs.org/",
        "npm": "https://nodejs.org/",
    }
    bullets = "\n".join(f"  - {c}: {urls[c]}" for c in missing)
    return (
        "[red-team-mcp] Missing required tool(s) for first-time install:\n"
        f"{bullets}\n"
        "Install them, ensure they are on PATH, then retry."
    )
