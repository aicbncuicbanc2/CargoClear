"""Thin wrapper around the provided loader.py Inbox interface.

Once the dataset ZIP is extracted into data/ (or the Docker dataset
server is running), this exposes the same `Inbox` interface documented
in the problem statement:

    from loader import Inbox
    inbox = Inbox("data")  # or Inbox("http://localhost:8080")
    for email in inbox: ...
    inbox.read_text(path)

`loader.py` ships with the dataset bundle itself, so it is dropped into
this package once we have it rather than hand-written here.
"""

from app.config import settings


def get_inbox():
    try:
        from loader import Inbox  # provided by the dataset bundle
    except ImportError as exc:
        raise RuntimeError(
            "loader.py not found yet — extract the dataset ZIP into data/ "
            "(it ships its own loader.py) before calling get_inbox()."
        ) from exc

    return Inbox(settings.dataset_source)
