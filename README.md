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
| Fuelix   | `FUELIX_API_KEY`    |

Example `.env` file:

```env
FUELIX_API_KEY=...
```

## Run

# Fuelix (default model: gemini-3-pro-preview)
```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621
```

# Fuelix with a different model
```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621 --model gemini-3-pro-preview
```