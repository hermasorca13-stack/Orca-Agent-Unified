# Orca ↔ Termux Bridge — Research & Design (2026)

> **Why this doc exists.** Captures the design decisions for the
> bidirectional bridge between the Orca Agent (Telegram bot) and a
> phone running Termux. Read this before touching `tools/termux_*`.

## Goal

Let the user control their **phone** (and any device they SSH into
via Termux) from **anywhere in the world** through the Orca Telegram
bot. The phone does not need a public IP, port forwarding, or a
Telegram bot of its own.

The bot should be able to:

- Run shell commands on the phone (`/termux run uname -a`)
- Read phone state (`/termux battery`, `/termux wifi`, `/termux storage`)
- Trigger Termux:API features (`/termux notify <msg>`, `/termux location`)
- Receive **spontaneous events** from the phone (battery low,
  task done, location changed) and forward them to the user's
  Telegram chat

The phone should be able to:

- Receive commands from the bot even when it's behind NAT
- Queue commands while offline, process them when it reconnects
- Push events back to the bot without waiting for a poll

## Architecture (2026)

```
Telegram user
     │  (Telegram Bot API)
     ▼
┌─────────────────────────────┐         ┌──────────────────────┐
│ Orca Bot (this repo)        │         │ Termux on phone      │
│  ┌──────────────────────┐   │  HTTP   │  ┌────────────────┐  │
│  │ skills/termux_skill │──▶│◀───────▶│  │termux_bridge.py│  │
│  │   /termux battery    │   │ poll    │  │  (Python, ~10KB)│  │
│  │   /termux run ...    │   │         │  └───────┬────────┘  │
│  │   /termux notify ... │   │         │          │           │
│  └──────────┬───────────┘   │         │          ▼           │
│             │               │         │  Termux:API + shell   │
│  ┌──────────▼───────────┐   │         │  (battery, location,  │
│  │ tools/termux_server  │   │         │   notify, camera...)  │
│  │   FastAPI on :8765   │   │         └──────────────────────┘
│  │   + JSONL queue      │   │
│  └──────────────────────┘   │
└─────────────────────────────┘
```

The transport is **HTTP polling** with optional `POST /event` for
spontaneous push. No persistent connection required, no tunnel
required, no public IP required.

## Transport choice: HTTP polling (not WebSocket, not MQTT, not SSH)

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| HTTP polling | works through any NAT, easy to debug with curl, no tunnel | 1-5s latency | ✅ chosen |
| WebSocket | low latency | requires tunnel, fragile on cellular | rejected |
| MQTT | pub/sub, IoT-friendly | external broker dep, auth complexity | rejected |
| SSH reverse tunnel | lowest latency, most flexible | user must have a server, port forwarding | rejected |
| Telegram-as-transport | no server needed | needs a second bot, eats into rate limits | rejected |
| GitHub Gist as queue | free, no server | 5-10s latency, rate limited | rejected |

Polling every **3 seconds** gives ~3s worst-case latency with zero
infrastructure. The user can tune `TERMUX_BRIDGE_POLL` if they want
faster.

## Auth model

A single shared secret in the `Authorization: Bearer <token>`
header. The token is `TERMUX_BRIDGE_TOKEN`, set in `.env` on the
Orca side and in `termux_bridge.json` on the phone side.

If the token is empty, the server refuses to start. This prevents
accidentally exposing the bridge without auth.

## Queue (Orca side)

Pending commands are stored in a JSONL file at
`data/termux_queue.jsonl`. Each line is one command:

```json
{"id": "abc123", "chat_id": 12345, "subcommand": "battery",
 "args": [], "created_at": 1717380000.0, "status": "pending"}
```

The phone reads new entries on each poll (filtered by status).
When the phone posts a result, the server marks the entry
`status: "completed"` and stores the output.

The queue is file-based (not a database) for two reasons:
- No new dependency (SQLite is overkill)
- Easy to inspect with `cat` / `jq`

Thread safety: FastAPI runs single-threaded by default for our
endpoints, so the only sync point is the file. We use
`threading.Lock()` to guard read-modify-write.

## Phone-side daemon (`tools/termux_bridge.py`)

Single-file Python 3 script. No external deps beyond stdlib
(urllib, json, subprocess, time, logging). Designed to run in
Termux as a long-lived process.

```bash
# Install on phone
pkg install python
mkdir -p ~/orca_bridge
cd ~/orca_bridge
# Copy termux_bridge.py + termux_bridge.json
# Then:
nohup python termux_bridge.py &
# Or use Termux:Boot to start on phone boot
```

The daemon:

1. Polls Orca `GET /pending` every 3s
2. For each pending command, executes via Termux:API
3. Posts `POST /result` with the output
4. Periodically posts `POST /event` with phone health
   (battery %, storage %, uptime)
5. Auto-reconnects on network failure
6. Logs to `~/orca_bridge/bridge.log`

## Subcommand set

| Subcommand | Termux:API / shell | Description |
|------------|--------------------|-------------|
| `battery` | `termux-battery-status` | battery %, status, temperature |
| `wifi` | `termux-wifi-connectioninfo` | SSID, IP, link speed |
| `location` | `termux-location` | GPS lat/lon/accuracy |
| `notify <msg>` | `termux-notification` | show phone notification |
| `clipboard` | `termux-clipboard-get` | get clipboard text |
| `toast <msg>` | `termux-toast` | short toast popup |
| `run <cmd>` | `subprocess` | run any shell command |
| `vibrate <ms>` | `termux-vibrate` | vibrate the phone |
| `uptime` | `uptime -p` | phone uptime |
| `storage` | `df -h ~` | storage info |
| `wake` | `termux-wake-lock` | wake + hold screen |
| `speak <text>` | `termux-tts-speak` | TTS via Android TTS engine |
| `torch [on\|off]` | `termux-torch` | toggle flashlight |
| `share <text>` | `termux-share` | open share sheet |
| `ping` | shell echo | health check |

## Error model

Every function returns a dict with `ok: bool` and either `result`
or `error`. The bot formats the error for the user. Examples:

```python
{"ok": False, "error": "termux-api not installed", "hint": "pkg install termux-api"}
{"ok": False, "error": "no network", "retry_after_seconds": 5}
{"ok": True, "result": {"battery": 87, "status": "discharging"}}
```

## Security

- Bearer token in `Authorization` header
- Token is required (server refuses to start without it)
- Command output is capped at 4 KB before being sent to Telegram
  (Telegram's message limit is 4096 chars; we leave room for
  formatting)
- Phone-side: the daemon runs with the same permissions as the
  Termux user. `/termux run` can do anything — this is by design
  (it's the user's own phone)
- All payloads are validated on the server side (pydantic models
  in FastAPI)

## Latency budget

- Network round trip (phone → server): ~200ms over WiFi, ~500ms
  over cellular
- Server processing: <5ms
- Phone-side command execution: 50ms (battery) to 5s (location
  fix)
- Telegram delivery: 100-500ms

End-to-end: ~1s typical, 5s worst case for location fix.

## Testing strategy

- **Unit tests** with mocked HTTP: `tests/test_termux_bridge.py`
  (daemon), `tests/test_termux_server.py` (FastAPI endpoints)
- **Integration test** with `TestClient`: 5 commands round-trip
  through the server
- **Smoke test** (gated on `TERMUX_BRIDGE_LIVE=1`): real HTTP
  against a running server, with `termux-api` commands mocked
  via env var

## 2026 techniques used

1. **File-based JSONL queue** — no SQLite, no Redis, just files
2. **Bearer-token auth** — same model as GitHub PATs / Telegram
   bot tokens
3. **Defensive coercion** — every function returns a dict, never
   raises
4. **Polling with backoff** — exponential backoff on network
   errors, capped at 30s
5. **Async FastAPI** — handles concurrent phone polls
6. **Pydantic models** for request validation
7. **Loguru for structured logging** on both sides
8. **Idempotent result posting** — re-POSTing the same result is
   a no-op (id-keyed)

## Future work (out of scope for v1)

- WebSocket support for sub-second latency
- Cron-style scheduled tasks ("every morning at 7am, send battery
  status to Telegram")
- File transfer (send a file from phone → Telegram as document)
- Voice call integration (Termux:API has `termux-telephony-call`)
- Multi-phone support (a single bot controlling a fleet of devices)
