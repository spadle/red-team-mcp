"""MCP server exposing three red-team tools over stdio.

Registered tools:
  - adversarial_review(subject, depth)  -> ruthless flaw-finding
  - devils_advocate(proposal)           -> argue the opposite side
  - red_team_code(code, language, context) -> security/correctness critique

Backend: any OpenAI-compatible /v1/chat/completions endpoint. Configured via
CODEX_PROXY_URL, CODEX_PROXY_KEY, CODEX_MODEL env vars (see codex_proxy.py).
"""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from .codex_proxy import BackendConfig, make_client, reachability_error
from .prompts import (
    ADVERSARIAL_REVIEW,
    DEPTH_MODIFIERS,
    DEVILS_ADVOCATE,
    RED_TEAM_CODE,
)

mcp = FastMCP("red-team")


def _call(system: str, user: str) -> str:
    cfg = BackendConfig.from_env()
    err = reachability_error(cfg)
    if err:
        return err
    client = make_client(cfg)
    resp = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content or ""


@mcp.tool()
def adversarial_review(
    subject: str,
    depth: Literal["quick", "medium", "deep"] = "medium",
) -> str:
    """Ruthlessly review a claim, plan, or design for flaws. Returns a critique
    with unstated-assumption audit, edge cases, counter-examples, and a ranked
    top-3 problem list. Use when you want a second model to stress-test an
    idea before you commit to it.

    Args:
      subject: The claim, plan, or design to review. Self-contained prose.
      depth: "quick" (top 3 only), "medium" (default, balanced), "deep" (exhaustive with test suggestions).
    """
    system = ADVERSARIAL_REVIEW + DEPTH_MODIFIERS[depth]
    return _call(system, subject)


@mcp.tool()
def devils_advocate(proposal: str) -> str:
    """Argue the opposite side of a proposal, seriously and vigorously. Returns
    the strongest case AGAINST the proposal with anticipated counter-arguments
    refuted. Use when you want to pressure-test a decision by hearing the best
    possible opposition before committing.

    Args:
      proposal: The proposal, decision, or position to argue against.
    """
    return _call(DEVILS_ADVOCATE, proposal)


@mcp.tool()
def red_team_code(
    code: str,
    language: str | None = None,
    context: str | None = None,
) -> str:
    """Security- and correctness-focused code review. Returns exploit-oriented
    findings ranked by (exploitability x impact), each with location, trigger,
    and concrete fix. Skips style and praise.

    Args:
      code: The source code to review. Include enough context (imports, types)
            for findings to be specific.
      language: Optional language hint (e.g. "python", "typescript", "go"). If
                omitted, the reviewer will infer from the code.
      context: Optional surrounding context — what the code is supposed to do,
               known constraints, deployment environment. Helps the reviewer
               judge severity.
    """
    header_parts = []
    if language:
        header_parts.append(f"Language: {language}")
    if context:
        header_parts.append(f"Context: {context}")
    header = "\n".join(header_parts)
    payload = f"{header}\n\n```\n{code}\n```" if header else f"```\n{code}\n```"
    return _call(RED_TEAM_CODE, payload)


def _run_install() -> int:
    """One-time managed-mode setup: clone codex-proxy, npm install, build web UI,
    seed a random bearer token, spawn, print the login URL."""
    import sys as _sys

    from .bootstrap import get_lifecycle

    lc = get_lifecycle()
    print("[red-team-mcp] installing codex-proxy backend (first run takes ~5 min)...", file=_sys.stderr)
    ok, err = lc.install()
    if not ok:
        print(err, file=_sys.stderr)
        return 1
    print("[red-team-mcp] install complete. starting codex-proxy...", file=_sys.stderr)
    ok, err = lc.ensure_running()
    if not ok:
        print(err, file=_sys.stderr)
        return 1
    print(
        f"[red-team-mcp] codex-proxy is running at http://localhost:{lc.port}/\n"
        f"[red-team-mcp] open that URL in a browser and log in with your ChatGPT account.\n"
        f"[red-team-mcp] then add the MCP server to your client (see README). you are done.",
        file=_sys.stderr,
    )
    return 0


def main() -> None:
    """Entry point registered by pyproject.toml [project.scripts]."""
    import sys as _sys

    if len(_sys.argv) > 1:
        cmd = _sys.argv[1]
        if cmd in ("install", "setup"):
            _sys.exit(_run_install())
        if cmd in ("-h", "--help", "help"):
            print(
                "red-team-mcp — MCP server with three contrarian tools.\n\n"
                "Usage:\n"
                "  red-team-mcp             # run the MCP server (stdio)\n"
                "  red-team-mcp install     # one-time: clone + build codex-proxy, generate key, start it\n"
                "\n"
                "Env vars:\n"
                "  CODEX_PROXY_URL   default http://localhost:8080/v1 (set to point elsewhere)\n"
                "  CODEX_PROXY_KEY   auto-loaded from ~/.red-team-mcp/proxy.key after `install`\n"
                "  CODEX_MODEL       default gpt-5.4\n"
                "  CODEX_PROXY_AUTO  default true; set false to disable managed auto-start\n"
                "  RED_TEAM_MCP_HOME default ~/.red-team-mcp/\n",
                file=_sys.stderr,
            )
            _sys.exit(0)

    mcp.run()


if __name__ == "__main__":
    main()
