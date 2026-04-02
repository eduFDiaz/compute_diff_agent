# compute-diff-agent

This repo is managed with **uv**.

## Setup

1) Install uv (if needed):
- https://docs.astral.sh/uv/

2) Create/sync the virtual environment:

```bash
uv sync
```

3) Provide your API key(s) (either environment variable or `.env` file):

| Provider | Environment variable |
|----------|---------------------|
| OpenAI   | `OPENAI_API_KEY`    |
| Fuelix   | `FUELIX_API_KEY`    |

Example `.env` file:

```env
OPENAI_API_KEY=...
FUELIX_API_KEY=...
```

## Run

```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621
```

# OpenAI (default, unchanged behaviour)
```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621
```

# Ollama phi4-mini (local)
```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621 --provider ollama
```

# Ollama with a different model
```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621 --provider ollama --model qwen3.5
```

# Fuelix (default model: claude-sonnet-4-6)
```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621 --provider fuelix
```

# Fuelix with a different model
```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621 --provider fuelix --model claude-opus-4-5
```