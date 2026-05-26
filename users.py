import re
from dataclasses import dataclass
from datetime import date
from typing import Literal


Gender = Literal["male", "female"]

_NICKNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}[a-z0-9]$|^[a-z0-9]$")


@dataclass(frozen=True)
class UserConfig:
    user_id: int
    nickname: str
    name: str
    email: str
    date_of_birth: date
    gender: Gender
    telegram_id: int | None = None
    tokens: str | None = None  # JSON string of DI OAuth tokens


def validate_nickname(nickname: str) -> str:
    slug = nickname.strip().lower()
    if not _NICKNAME_RE.match(slug):
        raise ValueError(
            "nickname must be 1-32 lowercase letters, digits, hyphens, or underscores"
        )
    return slug


def validate_name(name: str) -> str:
    value = name.strip()
    if not value:
        raise ValueError("name is required")
    if len(value) > 128:
        raise ValueError("name must be at most 128 characters")
    return value


def validate_gender(gender: str) -> Gender:
    value = gender.strip().lower()
    if value not in ("male", "female"):
        raise ValueError("gender must be male or female")
    return value  # type: ignore[return-value]
