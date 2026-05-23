import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UserConfig:
    user_id: str
    email: str
    password: str
    token_path: str


def load_users() -> list[UserConfig]:
    base = os.environ.get("GARMIN_TOKEN_CACHE_PATH", "/data/garmin_tokens")
    users: list[UserConfig] = []

    email1 = os.environ.get("GARMIN_USER_1_EMAIL") or os.environ.get("GARMIN_EMAIL")
    password1 = os.environ.get("GARMIN_USER_1_PASSWORD") or os.environ.get(
        "GARMIN_PASSWORD"
    )
    if email1 and password1:
        uid1 = os.environ.get("GARMIN_USER_1_ID", "user1")
        users.append(
            UserConfig(
                user_id=uid1,
                email=email1,
                password=password1,
                token_path=_token_path(base, uid1),
            )
        )

    email2 = os.environ.get("GARMIN_USER_2_EMAIL")
    password2 = os.environ.get("GARMIN_USER_2_PASSWORD")
    if email2 and password2:
        uid2 = os.environ.get("GARMIN_USER_2_ID", "user2")
        users.append(
            UserConfig(
                user_id=uid2,
                email=email2,
                password=password2,
                token_path=_token_path(base, uid2),
            )
        )

    if not users:
        raise RuntimeError(
            "No Garmin users configured. Set GARMIN_EMAIL/GARMIN_PASSWORD "
            "and/or GARMIN_USER_2_EMAIL/GARMIN_USER_2_PASSWORD."
        )
    return users


def _token_path(base: str, user_id: str) -> str:
    legacy = os.path.join(base, "garmin_tokens.json")
    path = os.path.join(base, user_id)
    if user_id == "user1" and os.path.isfile(legacy) and not os.path.isdir(path):
        return base
    return path
