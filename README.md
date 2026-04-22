# red-team-mcp

An MCP server giving Claude Code (or any MCP client) a **second model with a contrarian prompt** — for when you want your primary agent to stress-test a plan, hear the best opposing argument, or get an exploit-oriented code review before shipping.

Three tools, one server, pluggable text backend. Works out of the box against your ChatGPT account (via [codex-proxy](https://github.com/icebear0828/codex-proxy), auto-installed) or any OpenAI-compatible endpoint.

## Tools

| Tool                          | Purpose                                                                      |
| ----------------------------- | ---------------------------------------------------------------------------- |
| `red-team/adversarial_review` | Ruthlessly find flaws in a claim/plan/design. Ranked top-3 problems.         |
| `red-team/devils_advocate`    | Argue the strongest possible opposite side of a proposal.                    |
| `red-team/red_team_code`      | Security + correctness code review. Exploit-oriented, fix-concrete.          |

All three deliberately do not praise, hedge, or both-sides: their job is to push back.

## Install (managed mode — recommended)

**Requirements:** Python 3.10+, Node.js 18+, git, a ChatGPT account (free tier is fine).

### One-time setup

```bash
uvx red-team-mcp install
```

This:
1. Clones [codex-proxy](https://github.com/icebear0828/codex-proxy) to `~/.red-team-mcp/codex-proxy/`
2. `npm install` + builds the web UI
3. Generates a random local bearer token (written to `~/.red-team-mcp/proxy.key`)
4. Starts codex-proxy bound to `127.0.0.1:8080`
5. Prints the login URL

Takes ~5 minutes on first run. Open the printed URL in a browser and sign in with your ChatGPT account.

### Register with Claude Code

```bash
claude mcp add red-team -- uvx red-team-mcp
```

Or edit `~/.claude.json`:

```jsonc
{
  "mcpServers": {
    "red-team": {
      "command": "uvx",
      "args": ["red-team-mcp"]
    }
  }
}
```

Restart Claude Code. You should see `red-team/adversarial_review`, `red-team/devils_advocate`, and `red-team/red_team_code` in the tool list. **No API key configuration needed** — the MCP server auto-loads the generated token from `~/.red-team-mcp/proxy.key`. If codex-proxy ever stops (e.g. after a reboot), the MCP server will transparently respawn it.

## Install (BYO mode — advanced)

If you'd rather point at your own OpenAI-compatible endpoint (OpenAI, OpenRouter, LM Studio, etc.), skip the `install` step and configure the MCP server directly:

```jsonc
{
  "mcpServers": {
    "red-team": {
      "command": "uvx",
      "args": ["red-team-mcp"],
      "env": {
        "CODEX_PROXY_URL": "https://api.openai.com/v1",
        "CODEX_PROXY_KEY": "sk-...",
        "CODEX_MODEL": "gpt-4o"
      }
    }
  }
}
```

Lifecycle management is skipped when `CODEX_PROXY_URL` is not the default localhost — the endpoint must already be reachable.

## Configuration (env vars)

| Var                 | Default                           | Notes                                                                 |
| ------------------- | --------------------------------- | --------------------------------------------------------------------- |
| `CODEX_PROXY_URL`   | `http://localhost:8080/v1`        | Any OpenAI-compatible base URL. Non-default disables managed mode.    |
| `CODEX_PROXY_KEY`   | *(auto-loaded in managed mode)*   | Bearer token. Required in BYO mode, ≥4 chars.                         |
| `CODEX_MODEL`       | `gpt-5.4`                         | Model ID your backend recognizes.                                     |
| `CODEX_PROXY_AUTO`  | `true`                            | Set `false` to disable managed auto-start even for the default URL.   |
| `RED_TEAM_MCP_HOME` | `~/.red-team-mcp`                 | Override where clone, pidfile, log, and key live.                     |

### Example: OpenRouter (Claude-grade tool discipline)

```
CODEX_PROXY_URL=https://openrouter.ai/api/v1
CODEX_PROXY_KEY=sk-or-...
CODEX_MODEL=anthropic/claude-sonnet-4.6
```

### Example: local LM Studio

```
CODEX_PROXY_URL=http://localhost:1234/v1
CODEX_PROXY_KEY=not-needed-but-still-≥4-chars
CODEX_MODEL=qwen2.5-coder-32b-instruct
```

## Usage from Claude Code

Prompt patterns that work well:

> "Before we commit to this design, use `red-team/adversarial_review` on it, then decide whether to proceed."

> "I'm leaning toward X. Get a `red-team/devils_advocate` take on X, then help me weigh it."

> "Run `red-team/red_team_code` on `src/auth/session.py` — focus on what a malicious client could do."

Claude will marshal the right input, call the tool, read the critique, and integrate it.

## What lives where

```
~/.red-team-mcp/
├── codex-proxy/            # cloned backend
├── codex-proxy.pid         # last spawned PID
├── codex-proxy.log         # captured stdout + stderr
└── proxy.key               # auto-generated bearer token (mode 600 recommended)
```

Remove the whole directory to fully uninstall. `uvx` takes care of the Python package cache itself.

## Development

```bash
git clone https://github.com/spadle/red-team-mcp
cd red-team-mcp
uv sync
uv run red-team-mcp install         # one-time backend setup
uv run red-team-mcp                 # runs the MCP server on stdio
```

Project layout:

```
red-team-mcp/
├── pyproject.toml
├── README.md
├── src/red_team_mcp/
│   ├── __init__.py
│   ├── server.py           # MCP registration (FastMCP) + install subcommand
│   ├── prompts.py          # system prompts — one place to audit/tune
│   ├── codex_proxy.py      # OpenAI client + reachability/login probe
│   └── bootstrap.py        # codex-proxy lifecycle (install, spawn, health)
```

The prompts are deliberately in a single audit-friendly file so you can fork and tune them without touching server code.

## Roadmap

- **v0.3** Optional fourth tool `steelman(position)` — honest counterpart to `devils_advocate`, for when you want the strongest version of a view before critiquing it.
- **v0.3** Prompt overrides via `~/.red-team-mcp/prompts.d/*.md` so users can tune the critic without forking.
- **v0.3** Per-tool model override (`DEVILS_ADVOCATE_MODEL`, `RED_TEAM_CODE_MODEL`) so you can route code review to a code-tuned model and argumentation to a general one.
- **v0.4** Publish to PyPI so `uvx red-team-mcp` works without `--from git+https://...`.

## License

MIT
