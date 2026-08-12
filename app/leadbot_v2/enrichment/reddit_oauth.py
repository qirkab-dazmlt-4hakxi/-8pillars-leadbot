from __future__ import annotations

import os
import requests


class RedditOAuthClient:
    BASE = "https://oauth.reddit.com"

    def __init__(self) -> None:
        self.token = os.getenv("REDDIT_ACCESS_TOKEN")
        self.user_agent = os.getenv(
            "REDDIT_USER_AGENT",
            "8PillarsLeadIntelligence/2.0",
        )

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def get_json(self, path: str) -> dict | list | None:
        if not self.configured:
            return None

        if not path.startswith("/"):
            path = "/" + path

        r = requests.get(
            self.BASE + path,
            headers={
                "Authorization": f"bearer {self.token}",
                "User-Agent": self.user_agent,
            },
            timeout=15,
        )

        if r.status_code != 200:
            return None

        return r.json()
