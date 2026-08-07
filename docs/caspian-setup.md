# Caspian setup for Slack and Telegram

This guide follows the live Caspian integration guide and `caspian-sdk` Python client as inspected on **6 August 2026**. Re-check [the live guide](https://api.trycaspianai.com/SKILL.md) before a submission demo because supported providers can change.

## Verified SDK contract

```python
from caspian_sdk import CommClient

client = CommClient()  # CASPIAN_API_KEY + CASPIAN_BASE_URL

client.connect_telegram(bot_token="...")
client.install_slack(display_name="PatchPilot")

@client.on_message
def shared_handler(message):
    # id, conversation_id, connection_id, channel, sender, text
    message.reply("Reply on the originating channel")

client.listen(concurrency="queue")
```

PatchPilot implements this in `apps/api/patchpilot/caspian/adapter.py`. It uses `client.send_message(conversation_id, text=...)` for proactive updates to an existing conversation.

## 1. Create a Caspian project key

You can use the official CLI:

```bash
pipx install caspian-cli
caspian init
```

Or mint a sandbox key without signup:

```bash
curl -s -X POST https://api.trycaspianai.com/v1/projects/sandbox \
  -H 'Content-Type: application/json' \
  -d '{"name":"patchpilot"}'
```

Store the returned key locally:

```dotenv
CASPIAN_API_KEY=comm_sandbox_...
CASPIAN_BASE_URL=https://api.trycaspianai.com
CASPIAN_ENABLED=true
```

Do not commit `.env`.

Discover what the hosted gateway currently supports:

```bash
curl -s https://api.trycaspianai.com/v1/channels \
  -H "Authorization: Bearer $CASPIAN_API_KEY"
```

## 2. Connect Telegram

1. Open Telegram and message `@BotFather`.
2. Send `/newbot`.
3. Choose a display name and unique username.
4. Copy the token from BotFather into `.env`:

```dotenv
CASPIAN_TELEGRAM_BOT_TOKEN=7123456789:AAE...
```

On API startup PatchPilot calls exactly:

```python
client.connect_telegram(bot_token=settings.caspian_telegram_bot_token)
```

Caspian registers and verifies the Telegram webhook. A 409 means the bot is already connected to another project. A 422 identifying `bot_token` means it is absent or malformed.

## 3. Connect Slack

Caspian currently provides quick, branded OAuth, and Socket Mode paths. Quick mode is the recommended hackathon setup.

### Quick mode

Configure:

```dotenv
CASPIAN_SLACK_MODE=quick
CASPIAN_SLACK_DISPLAY_NAME=PatchPilot
CASPIAN_SLACK_ICON_URL=https://your-public-icon.png
```

PatchPilot calls:

```python
client.install_slack(display_name="PatchPilot", icon_url="...")
```

The returned secret-free configuration summary includes `authorize_url`. Open it, select the Slack workspace, and authorize. The connection becomes active after OAuth completes.

### Branded OAuth app

At <https://api.slack.com/apps>, create an app from scratch.

1. OAuth redirect URL: `https://api.trycaspianai.com/v1/oauth/slack/callback`
2. Bot scopes: `chat:write`, `chat:write.customize`, `channels:history`, `im:history`, `app_mentions:read`
3. Event Request URL: `https://api.trycaspianai.com/internal/providers/slack/webhooks`
4. Bot events: `message.channels`, `message.im`, `app_mention`
5. Copy Client ID, Client Secret, and Signing Secret into `.env`.

```dotenv
CASPIAN_SLACK_MODE=branded
CASPIAN_SLACK_CLIENT_ID=
CASPIAN_SLACK_CLIENT_SECRET=
CASPIAN_SLACK_SIGNING_SECRET=
```

PatchPilot calls `client.connect_slack(slack_client_id=..., slack_client_secret=..., slack_signing_secret=...)`. Open the returned authorization URL.

### Socket Mode

Create a Slack bot token (`xoxb-`) and app token (`xapp-`, `connections:write`), then configure:

```dotenv
CASPIAN_SLACK_MODE=socket
CASPIAN_SLACK_BOT_TOKEN=xoxb-...
CASPIAN_SLACK_APP_TOKEN=xapp-...
```

PatchPilot calls `client.connect_slack(bot_token=..., app_token=...)`.

## 4. Start and verify

```bash
docker compose up --build
```

Send to both Slack and Telegram:

```text
/patchpilot help
```

Each should receive the same command help from the one handler.

Start in Slack:

```text
/patchpilot start owner/repository#143
```

Approve the returned task from Telegram:

```text
/patchpilot approve <task-id>
```

Check `http://localhost:3000/settings/channels` for connection state and `http://localhost:3000/tasks/<task-id>` for the audit trail.

## Webhook and idempotency behavior

- Slack and Telegram webhooks terminate at Caspian, not the PatchPilot API.
- Caspian verifies platform signatures and emits normalized events.
- `client.listen()` polls ordered events and dispatches the single handler.
- PatchPilot persists `(channel, message_id)` before executing a command.
- The SDK deduplicates within a run; the database constraint covers process restarts.
- PatchPilot stores conversation IDs for proactive plan/final updates, never platform tokens.

## Troubleshooting

- No handler activity: verify `CASPIAN_ENABLED=true`, key/base URL, and API logs.
- Telegram 409: create a new bot or disconnect the existing project.
- Slack quick install returns 400: the shared app is unavailable on that gateway; use branded OAuth or Socket Mode.
- Slack authorization is pending: open the returned `authorize_url` and choose a workspace.
- Only one channel works: check the `/api/channels` response and secret-free configuration summary.
- Duplicate command produces no second reply: expected idempotency behavior.

Official sources: [live integration guide](https://api.trycaspianai.com/SKILL.md), [SDK repository](https://github.com/TryCaspian/caspian-sdk), and [Python client source](https://github.com/TryCaspian/caspian-sdk/blob/main/sdks/python/src/caspian_sdk/client.py).

