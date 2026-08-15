import pytest

from patchpilot.services.commands import CommandError, parse_command


@pytest.mark.parametrize(
    ("text", "name", "argument"),
    [
        ("/patchpilot start octo/demo#143", "start", "octo/demo#143"),
        ("Analyze issue 143 in octo/demo", "start", "octo/demo#143"),
        ("/patchpilot approve 33333333", "approve", "33333333"),
        ("What is the status of task 33333333?", "status", "33333333"),
        ("/patchpilot help", "help", None),
    ],
)
def test_parse_command(text, name, argument):
    command = parse_command(text)
    assert command.name == name
    assert command.argument == argument


def test_reject_requires_reason_is_preserved():
    command = parse_command("/patchpilot reject 33333333 scope is too large")
    assert command.reason == "scope is too large"


def test_leading_slack_app_mention_is_ignored():
    assert parse_command("<@U123456> patchpilot help").name == "help"


def test_slack_app_mention_inside_argument_is_preserved():
    command = parse_command("patchpilot reject abc123 <@U123456> review needed")
    assert command.name == "reject"
    assert command.reason == "<@U123456> review needed"


def test_unsupported_command_is_clear():
    with pytest.raises(CommandError, match="Unsupported command"):
        parse_command("write me a poem")
