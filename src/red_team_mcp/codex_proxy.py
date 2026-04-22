"""Client + reachability check for the OpenAI-compatible backend.

Two modes, auto-selected from env:

  * Managed (default): backend URL is the default localhost:8080. We auto-start
    codex-proxy via bootstrap.Lifecycle.ensure_running(), and auto-load the
    API key from ~/.red-team-mcp/proxy.key when CODEX_PROXY_KEY is unset. Zero
    config for the user after `red-team-mcp install`.

  * BYO: user sets CODEX_PROXY_URL (not localhost) or CODEX_PROXY_KEY
    explicitly. We trust them and do no lifecycle management — the backend
    must already be reachable.

Tools surface any error as a plain string so Claude Code can relay the
message to the user without wrapping or interpretation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from openai import OpenAI

from .bootstrap import get_lifecycle

DEFAULT_BASE_URL = "http://localhost:8080/v1"


@dataclass(frozen=True)
class BackendConfig:
    base_url: str
    api_key: str
    model: str
    managed: bool  # True when we auto-manage codex-proxy lifecycle

    @classmethod
    def from_env(cls) -> "BackendConfig":
        base_url = os.environ.get("CODEX_PROXY_URL", DEFAULT_BASE_URL)
        managed = _is_default_localhost(base_url) and _autostart_enabled()

        api_key = os.environ.get("CODEX_PROXY_KEY", "").strip()
        if not api_key and managed:
            # Auto-load the key that `red-team-mcp install` generated.
            keyfile = get_lifecycle().keyfile
            if keyfile.exists():
                api_key = keyfile.read_text().strip()

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=os.environ.get("CODEX_MODEL", "gpt-5.4"),
            managed=managed,
        )


def reachability_error(cfg: BackendConfig) -> str | None:
    """Return None if backend looks usable, else a human-readable error string
    that tools surface verbatim to Claude Code."""
    if cfg.managed:
        ok, err = get_lifecycle().ensure_running()
        if err:
            return err

    if not cfg.api_key:
        return (
            "[red-team-mcp] CODEX_PROXY_KEY env var is not set and no auto-generated "
            "key was found. Either run `uvx red-team-mcp install` (managed mode) or "
            "set CODEX_PROXY_KEY in your MCP client config (BYO mode)."
        )

    root = cfg.base_url.rstrip("/").removesuffix("/v1")
    try:
        r = httpx.get(f"{root}/", timeout=3.0)
    except httpx.HTTPError as exc:
        return (
            f"[red-team-mcp] Cannot reach backend at {root} ({exc}). "
            "In managed mode this usually means the auto-spawn failed — check "
            f"{get_lifecycle().logfile}. In BYO mode, verify your endpoint is up."
        )
    if r.status_code >= 500:
        return f"[red-team-mcp] Backend at {root} returned HTTP {r.status_code}."

    # Auth + login probe: minimal chat call. codex-proxy returns 401 when
    # not-logged-in or when the bearer key is wrong.
    try:
        client = make_client(cfg)
        client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": "ping"}],
            max_completion_tokens=1,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "401" in msg or ("invalid" in msg and "key" in msg):
            if cfg.managed:
                return (
                    f"[red-team-mcp] codex-proxy is running but not yet logged in with a "
                    f"ChatGPT account. Open {root}/ in a browser and sign in, then retry."
                )
            return (
                f"[red-team-mcp] Backend at {root} rejected the API key. "
                "Check CODEX_PROXY_KEY in your MCP client config."
            )
        return f"[red-team-mcp] Backend smoke-test failed: {exc}"
    return None


def make_client(cfg: BackendConfig) -> OpenAI:
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)


def _is_default_localhost(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return p.hostname in ("localhost", "127.0.0.1") and (p.port or 80) == 8080


def _autostart_enabled() -> bool:
    return os.environ.get("CODEX_PROXY_AUTO", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )
