from dataclasses import dataclass

import pytest

from patchpilot.caspian.adapter import CaspianGateway, normalize_caspian_message


@dataclass
class FakeMessage:
    id: str = "msg-1"
    conversation_id: str = "conv-1"
    connection_id: str = "connection-1"
    channel: str = "slack"
    sender: dict | None = None
    text: str | None = "/patchpilot help"


def test_normalizes_official_caspian_message_fields():
    normalized = normalize_caspian_message(
        FakeMessage(sender={"display_name": "Maya", "address": "U123"})
    )
    assert normalized.channel == "slack"
    assert normalized.sender == "Maya"
    assert normalized.message_id == "msg-1"
    assert normalized.conversation_id == "conv-1"


def test_rejects_unsupported_channel():
    with pytest.raises(ValueError, match="Unsupported"):
        normalize_caspian_message(FakeMessage(channel="email"))


def test_prefers_latest_active_connection_over_stale_pending_oauth():
    selected = CaspianGateway._select_connection(
        [
            {
                "id": "active-old",
                "channel": "slack",
                "status": "active",
                "created_at": "2026-08-09T15:42:00",
            },
            {
                "id": "active-current",
                "channel": "slack",
                "status": "active",
                "created_at": "2026-08-09T15:47:00",
            },
            {
                "id": "pending-newer",
                "channel": "slack",
                "status": "pending_oauth",
                "created_at": "2026-08-11T16:00:00",
            },
        ],
        "slack",
    )

    assert selected and selected["id"] == "active-current"


def test_reuses_pending_connection_instead_of_creating_another():
    selected = CaspianGateway._select_connection(
        [
            {
                "id": "pending-current",
                "channel": "slack",
                "status": "pending_oauth",
                "created_at": "2026-08-11T16:00:00",
            },
            {
                "id": "failed-old",
                "channel": "slack",
                "status": "failed",
                "created_at": "2026-08-11T15:00:00",
            },
        ],
        "slack",
    )

    assert selected and selected["id"] == "pending-current"
