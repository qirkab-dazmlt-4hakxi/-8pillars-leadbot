from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RedditAuthConfig:
    client_id: str | None
    client_secret: str | None
    username: str | None
    password: str | None
    user_agent: str

    @property
    def configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.user_agent
        )


def load_reddit_auth() -> RedditAuthConfig:
    return RedditAuthConfig(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv(
            "REDDIT_USER_AGENT",
            "8PillarsLeadIntelligence/2.0",
        ),
    )
