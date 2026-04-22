# red-team-mcp

An MCP server giving Claude Code (or any MCP client) a **second model with a contrarian prompt** — for when you want your primary agent to stress-test a plan, hear the best opposing argument, or get an exploit-oriented code review before shipping.

Three tools, one server, any OpenAI-compatible text backend.

## Tools

| Tool                  | Purpose                                                                      |
| --------------------- | ---------------------------------------------------------------------------- |
| `adversarial_review`  | Ruthlessly find flaws in a claim/plan/design. Ranked top-3 problems.         |
| `devils_advocate`     | Argue the strongest possible opposite side of a proposal.                    |
| `red_team_code`       | Security + correctness code review. Exploit-oriented, fix-concrete.          |

All three are backed by whatever OpenAI-compatible model you configure (see below). They deliberately do not praise, hedge, or both-sides: their job is to push back.

## Install

### Requirements
- Python 3.10+
- An OpenAI-compatible `/v1/chat/completions` endpoint. This project was built against [codex-proxy](https://github.com/icebear0828/codex-proxy) (wraps your ChatGPT account) but works with OpenAI, OpenRouter, or any local LLM server (LM Studio, Ollama, vLLM).

### Claude Code

```bash
claude mcp add red-team -- uvx red-team-mcp
```

Or edit `~/.claude.json` manually:

```jsonc
{
  "mcpServers": {
    "red-team": {
      "command": "uvx",
      "args": ["red-team-mcp"],
      "env": {
        "CODEX_PROXY_URL": "http://localhost:8080/v1",
        "CODEX_PROXY_KEY": "<your-proxy-api-key>",
        "CODEX_MODEL": "gpt-5.4"
      }
    }
  }
}
```

Restart Claude Code. You should see `red-team/adversarial_review`, `red-team/devils_advocate`, and `red-team/red_team_code` in its tool list.

### Other MCP clients
The server speaks MCP over stdio. Any MCP-compatible client that can spawn a process works — just point `command: uvx` and `args: ["red-team-mcp"]`.

## Configuration

All via environment variables:

| Var                 | Default                           | Notes                                                      |
| ------------------- | --------------------------------- | ---------------------------------------------------------- |
| `CODEX_PROXY_URL`   | `http://localhost:8080/v1`        | Any OpenAI-compatible base URL.                            |
| `CODEX_PROXY_KEY`   | *(required)*                      | Bearer token. For codex-proxy, match `proxy_api_key` in its `data/local.yaml`. For OpenAI/OpenRouter, use your real API key. Must be ≥4 chars. |
| `CODEX_MODEL`       | `gpt-5.4`                         | Model ID your backend recognizes.                          |

### Pointing at OpenAI directly
```
CODEX_PROXY_URL=https://api.openai.com/v1
CODEX_PROXY_KEY=sk-...
CODEX_MODEL=gpt-4o
```

### Pointing at OpenRouter
```
CODEX_PROXY_URL=https://openrouter.ai/api/v1
CODEX_PROXY_KEY=sk-or-...
CODEX_MODEL=anthropic/claude-sonnet-4.6
```

### Pointing at a local LLM (LM Studio)
```
CODEX_PROXY_URL=http://localhost:1234/v1
CODEX_PROXY_KEY=not-needed
CODEX_MODEL=qwen2.5-coder-32b-instruct
```

## Usage from Claude Code

Prompt patterns that work well:

> "Before we commit to this design, use `red-team/adversarial_review` on it, then decide whether to proceed."

> "I'm leaning toward X. Get a `red-team/devils_advocate` take on X, then help me weigh it."

> "Run `red-team/red_team_code` on `src/auth/session.py` — focus on what a malicious client could do."

Claude will marshal the right input, call the tool, read the critique, and integrate it into its response.

## Development

```bash
git clone https://github.com/spadle/red-team-mcp
cd red-team-mcp
uv sync
uv run red-team-mcp   # runs the server on stdio — use in an MCP client, not directly
```

Project layout:
```
red-team-mcp/
├── pyproject.toml
├── README.md
├── src/red_team_mcp/
│   ├── __init__.py
│   ├── server.py         # MCP registration (FastMCP)
│   ├── prompts.py        # system prompts (constants, easy to diff)
│   └── codex_proxy.py    # OpenAI client + reachability check
```

The prompts are deliberately kept in a single audit-friendly file so you can fork and tune them for your stack without touching server code.

## Roadmap

- **v0.2** Auto-manage codex-proxy lifecycle (clone on first run if missing, spawn detached, surface login URL as a tool-call error on first auth failure).
- **v0.2** Optional fourth tool `steelman(position)` — the honest counterpart to `devils_advocate`, for when you want the *strongest* version of a view before critiquing it.
- **v0.3** Prompt overrides via `~/.red-team-mcp/prompts.d/*.md` so users can tune the critic without forking.
- **v0.3** Per-tool model override (`DEVILS_ADVOCATE_MODEL`, `RED_TEAM_CODE_MODEL`) so you can route code review to a code-tuned model and argumentation to a general one.

## License

MIT
