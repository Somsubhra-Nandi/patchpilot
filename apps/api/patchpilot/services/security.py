import re
import shlex
from pathlib import PurePosixPath

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ALLOWED_EXECUTABLES = {
    "pytest",
    "ruff",
    "npm",
    "pnpm",
    "yarn",
    "python",
    "python3",
    "uv",
    "make",
    "cargo",
    "go",
}


def validate_repository_identifier(value: str) -> str:
    if not REPOSITORY_RE.fullmatch(value):
        raise ValueError("Repository must use the owner/name format")
    return value


def ensure_paths_allowed(paths: list[str], protected_paths: list[str]) -> None:
    normalized_protected = [PurePosixPath(item.strip("/")) for item in protected_paths]
    for raw_path in paths:
        path = PurePosixPath(raw_path.strip("/"))
        if ".." in path.parts or path.is_absolute():
            raise ValueError(f"Unsafe path: {raw_path}")
        if any(path == protected or protected in path.parents for protected in normalized_protected):
            raise ValueError(f"Protected path cannot be modified: {raw_path}")


def parse_validation_command(command: str) -> list[str]:
    if any(token in command for token in ("&&", "||", ";", "|", ">", "<", "`", "$(")):
        raise ValueError("Shell control operators are not permitted in validation commands")
    argv = shlex.split(command, posix=True)
    if not argv or argv[0] not in ALLOWED_EXECUTABLES:
        raise ValueError("Validation executable is not allowlisted")
    return argv

