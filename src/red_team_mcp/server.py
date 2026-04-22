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


def main() -> None:
    """Entry point registered by pyproject.toml [project.scripts]."""
    mcp.run()


if __name__ == "__main__":
    main()
