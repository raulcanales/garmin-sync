import re
from dataclasses import dataclass


_USER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}[a-z0-9]$|^[a-z0-9]$")


@dataclass(frozen=True)
class UserConfig:
    user_id: str
    nickname: str
    email: str
    tokens: str | None = None  # JSON string of DI OAuth tokens


def validate_user_id(user_id: str) -> str:
    slug = user_id.strip().lower()
    if not _USER_ID_RE.match(slug):
        raise ValueError(
            "user_id must be 1-32 lowercase letters, digits, hyphens, or underscores"
        )
    return slug


def validate_nickname(nickname: str) -> str:
    name = nickname.strip()
    if not name:
        raise ValueError("nickname is required")
    if len(name) > 64:
        raise ValueError("nickname must be at most 64 characters")
    return name
