# nochan (NapCatOpenCodeChannel)

A Python WebSocket server that bridges [NapCatQQ](https://github.com/NapNeko/NapCatQQ) and [OpenCode](https://github.com/sst/opencode) — chat with an AI coding assistant through QQ.

## Quick Start

```bash
# Install dependencies (requires uv and Python 3.12+)
uv sync

# Edit config.toml as needed, then start the server
uv run python main.py
```

## Configuration

See `config.toml` for all options. Key settings:

- `server.port` — WebSocket port for NapCatQQ to connect to
- `opencode.max_concurrent` — Max parallel AI processes (default 1)
- `logging.level` — Console log level; file always captures DEBUG

## QQ Commands

| Command | Description |
|---------|-------------|
| `/new`  | Start a new AI session (clears context) |
| `/help` | Show available commands |

In group chats, the bot must be @-mentioned to respond.

## Testing

```bash
uv run pytest tests/ -v
```

## Documentation

- [Product Spec](docs/product-v1.md) — Detailed v1 design
- [Dev Plan](docs/dev-plan-v1.md) — Step-by-step development plan
