from dataclasses import dataclass

import pytest

from patchpilot.caspian.adapter import normalize_caspian_message


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

