# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Structure

```
local-voice-ai/
├─ frontend/        # Next.js 15 + Tailwind + shadcn UI (pnpm)
├─ livekit_agent/   # Python voice agent (LiveKit Agents SDK, uv)
├─ livekit/         # LiveKit server config (Dockerfile)
├─ inference/       # Inference service Dockerfiles (llama/nemotron/whisper/kokoro)
└─ docker-compose.yml
```

## Commands

### Full stack (Docker)
```bash
# First run — choose CPU or GPU
./compose-up.sh           # Mac/Linux
./compose-up.ps1          # Windows

# Rebuild after code changes
docker compose down -v --remove-orphans
docker compose up --build

# With Whisper STT instead of Nemotron
docker compose --profile whisper up
```

### Agent (Python — `livekit_agent/`)
Uses `uv`. All commands run from `livekit_agent/`.
```bash
uv sync
uv run python src/agent.py download-files   # first run: downloads VAD + turn-detector models
uv run python src/agent.py console          # talk to agent in terminal
uv run python src/agent.py dev              # run for frontend/telephony use
uv run pytest                               # run evals
uv run ruff format                          # format
uv run ruff check                           # lint
```

### Frontend (`frontend/`)
```bash
pnpm install
pnpm dev     # http://localhost:3000
pnpm build
pnpm lint
pnpm format
```

## Architecture

The pipeline is: **browser → LiveKit (WebRTC) → Python agent → STT → LLM → TTS → browser**.

- `livekit_agent/src/agent.py` is the sole agent entrypoint. It wires `silero.VAD` + `MultilingualModel` turn detection + `openai.STT/LLM/TTS` plugins — all pointing at local inference containers via env vars.
- All inference services expose OpenAI-compatible APIs, so the agent plugins are swappable without code changes (just env vars).
- The frontend (`frontend/`) signs LiveKit tokens via `/api/connection-details` and returns `serverUrl` = `NEXT_PUBLIC_LIVEKIT_URL` (browser-reachable). The agent uses `LIVEKIT_URL` (container-internal `ws://livekit:7880`). These must be configured separately.
- `livekit_agent` container depends-on healthchecks for `llama_cpp` and `nemotron` — it won't start until both are ready (can take minutes on first boot while models download).
- Models are cached on disk: LLM under `inference/llama/models`, Nemotron under a named Docker volume.

## Local dev without Docker

Copy `.env.example` → `.env.local` in both `frontend/` and `livekit_agent/`, then point URLs at `localhost` ports (comments in `agent.py` show the localhost equivalents). Run the inference services separately or use the Docker stack while running the agent/frontend outside containers.

## Adding tools to the agent

Add `@function_tool()` methods to the `Assistant` class in `agent.py`. Follow TDD: write a test in `tests/test_agent.py` first using `AgentSession` + `result.expect` assertions, then implement. Tests use `inference.LLM(model="openai/gpt-4.1-mini")` as the judge LLM — requires a real `OPENAI_API_KEY` in env.

## Key env vars

| Var | Where set | Purpose |
|-----|-----------|---------|
| `LIVEKIT_URL` | agent `.env.local` / compose `.env` | Agent→LiveKit (internal) |
| `NEXT_PUBLIC_LIVEKIT_URL` | frontend `.env.local` | Browser→LiveKit URL |
| `LLAMA_HF_REPO` | compose `.env` | HF repo for LLM (supports `:quant` suffix) |
| `LLAMA_MODEL` / `LLAMA_MODEL_ALIAS` | agent env / compose | Must match; alias is what the API exposes |
| `STT_PROVIDER` | agent env | `nemotron` (default) or `whisper` |

## MCP server for LiveKit docs

```bash
claude mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```
