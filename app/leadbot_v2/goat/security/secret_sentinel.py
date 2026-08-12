from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass


BLOCKED_PATHS = (
    re.compile(r"(^|/)\.env($|\.)", re.I),
    re.compile(r"\.(pem|key|p12|pfx|jks|keystore|seed|mnemonic)$", re.I),
    re.compile(r"\.(db|sqlite|sqlite3)$", re.I),
    re.compile(r"(^|/)(secrets?|credentials?|wallet_private)(/|$)", re.I),
)

ALLOW_PATHS = {
    ".env.example",
    "app/.env.example",
}

SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Stripe live secret", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    ("OpenAI-style secret", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)

ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(
        api[_-]?key |
        auth[_-]?token |
        access[_-]?token |
        client[_-]?secret |
        app[_-]?secret |
        password |
        webhook[_-]?shared[_-]?secret |
        private[_-]?key
    )
    \s*[:=]\s*
    ["']?
    ([A-Za-z0-9+/=_\-.:]{12,})
    """
)

SAFE_MARKERS = {
    "change_me",
    "changeme",
    "example",
    "placeholder",
    "your_key_here",
    "your_secret_here",
}


@dataclass(frozen=True)
class Finding:
    path: str
    reason: str


def staged_files() -> list[str]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [x.strip() for x in result.stdout.splitlines() if x.strip()]


def staged_content(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f":{path}"],
        capture_output=True,
    )
    if result.returncode != 0:
        return ""

    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def scan_path(path: str) -> list[Finding]:
    findings: list[Finding] = []

    if path in ALLOW_PATHS or path.endswith("/.env.example"):
        return findings

    for pattern in BLOCKED_PATHS:
        if pattern.search(path):
            findings.append(
                Finding(path, "forbidden sensitive/runtime file type")
            )
            return findings

    text = staged_content(path)

    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(Finding(path, label))

    for match in ASSIGNMENT.finditer(text):
        value = match.group(2).lower()

        if not any(marker in value for marker in SAFE_MARKERS):
            findings.append(
                Finding(
                    path,
                    f"possible live credential assignment: {match.group(1)}",
                )
            )

    return findings


def main() -> int:
    findings: list[Finding] = []

    for path in staged_files():
        findings.extend(scan_path(path))

    if findings:
        print("\nGOAT SECRET SENTINEL: COMMIT BLOCKED")
        print("------------------------------------")

        for finding in findings:
            print(f"{finding.path}: {finding.reason}")

        print(
            "\nMove secrets into the approved secret store and stage again."
        )
        return 1

    print("GOAT SECRET SENTINEL: CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
