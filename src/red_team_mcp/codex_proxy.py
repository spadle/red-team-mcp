"""Client + reachability check for the OpenAI-compatible backend.

v0.1: BYO — reads CODEX_PROXY_URL / CODEX_PROXY_KEY / CODEX_MODEL from env
with sensible defaults. Tools return a clear error message if the backend
is unreachable or unauthenticated.

v0.2 TODO: auto-manage codex-proxy lifecycle (clone on first run if missing,
spawn detached, pidfile at ~/.red-team-mcp/codex-proxy.pid, health-check,
surface login instructions on first auth failure).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from openai import OpenAI


@dataclass(frozen=True)
class BackendConfig:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> "BackendConfig":
        # api_key is deliberately left unset if the env var is missing so that
        # reachability_error() can surface a clear, actionable message instead
        # of silently defaulting to a value baked into source (which is both a
        # secret-hygiene smell and a confusing failure mode).
        return cls(
            base_url=os.environ.get("CODEX_PROXY_URL", "http://localhost:8080/v1"),
            api_key=os.environ.get("CODEX_PROXY_KEY", "").strip(),
            model=os.environ.get("CODEX_MODEL", "gpt-5.4"),
        )


def reachability_error(cfg: BackendConfig) -> str | None:
    """Return None if backend looks usable, else a human-readable error string
    that tools can surface back to Claude Code verbatim."""
    if not cfg.api_key:
        return (
            "[red-team-mcp] CODEX_PROXY_KEY env var is not set. Configure it "
            "in your MCP client (e.g. ~/.claude.json 'env' block) to match the "
            "proxy_api_key in your codex-proxy data/local.yaml — or to your "
            "OpenAI / OpenRouter / other provider API key if pointing elsewhere."
        )
    root = cfg.base_url.rstrip("/").removesuffix("/v1")
    try:
        r = httpx.get(f"{root}/", timeout=3.0)
    except httpx.HTTPError as exc:
        return (
            f"[red-team-mcp] Cannot reach codex-proxy at {root} ({exc}).\n"
            "Install from https://github.com/icebear0828/codex-proxy and run "
            "`npm run dev` (or launch the desktop app), then log in at the "
            "dashboard URL it prints."
        )
    if r.status_code >= 500:
        return f"[red-team-mcp] codex-proxy at {root} returned HTTP {r.status_code}."
    # Auth-probe: hit /v1/chat/completions with a minimal request. On
    # "not logged in" codex-proxy returns 401 with an auth-required message.
    try:
        client = make_client(cfg)
        client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": "ping"}],
            max_completion_tokens=1,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "401" in msg or "invalid" in msg and "key" in msg:
            return (
                f"[red-team-mcp] codex-proxy rejected the API key at {root}. "
                "Check CODEX_PROXY_KEY matches the proxy_api_key in codex-proxy's "
                "data/local.yaml."
            )
        if "not logged" in msg or "authenticated" in msg:
            return (
                f"[red-team-mcp] codex-proxy is running but not logged in. "
                f"Open {root}/ in a browser and log in with your ChatGPT account."
            )
        return f"[red-team-mcp] Backend smoke-test failed: {exc}"
    return None


def make_client(cfg: BackendConfig) -> OpenAI:
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
