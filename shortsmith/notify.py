"""ntfy.sh push notifications. Free, no signup required."""
from __future__ import annotations
import base64
import urllib.request


def send(topic: str, title: str, body: str, priority: str = "default",
         tags: str = "rocket") -> bool:
    """Send a push to ntfy.sh/<topic>. Returns True on success."""
    if not topic:
        return False
    try:
        title.encode("latin-1")
        title_header = title
    except UnicodeEncodeError:
        title_header = (
            "=?utf-8?b?"
            + base64.b64encode(title.encode("utf-8")).decode("ascii")
            + "?="
        )
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://ntfy.sh/{topic}",
                data=body.encode("utf-8"),
                headers={
                    "Title": title_header,
                    "Priority": priority,
                    "Tags": tags,
                },
                method="POST",
            ),
            timeout=10,
        )
        return True
    except Exception:
        return False
