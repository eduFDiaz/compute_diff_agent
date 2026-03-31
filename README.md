# compute-diff-agent

This repo is managed with **uv**.

## Setup

1) Install uv (if needed):
- https://docs.astral.sh/uv/

2) Create/sync the virtual environment:

```bash
uv sync
```

3) Provide your API key (either environment variable or `.env` file):

- Environment variable: `OPENAI_API_KEY=...`
- Or create a `.env` file with:

```env
OPENAI_API_KEY=...
```

## Run

```bash
uv run python network_diff_prototype.py config.cfg target.cfg --vendor ekinops_one621
```
