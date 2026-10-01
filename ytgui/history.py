"""Download history persisted as JSON."""

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import List, Optional

from .logs import get_logger
from .paths import history_file

log = get_logger(__name__)
MAX_ITEMS = 1000


@dataclass
class HistoryItem:
    title: str
    url: str
    filepath: str = ""
    thumbnail: Optional[str] = None
    uploader: str = ""
    format_label: str = ""
    mode: str = "video"
    size: Optional[int] = None
    duration: Optional[float] = None
    finished_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryItem":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class HistoryStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or history_file()
        self._lock = threading.Lock()
        self.items: List[HistoryItem] = self._load()

    def _load(self) -> List[HistoryItem]:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                return [HistoryItem.from_dict(d) for d in raw if isinstance(d, dict) and d.get("url")]
        except (OSError, ValueError, TypeError) as exc:
            log.warning("Could not read history: %s", exc)
        return []

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps([asdict(i) for i in self.items], ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            log.error("Could not save history: %s", exc)

    def add(self, item: HistoryItem) -> None:
        with self._lock:
            self.items.insert(0, item)
            del self.items[MAX_ITEMS:]
            self._save()

    def remove(self, item_id: str) -> None:
        with self._lock:
            self.items = [i for i in self.items if i.id != item_id]
            self._save()

    def clear(self) -> None:
        with self._lock:
            self.items = []
            self._save()

    def search(self, text: str) -> List[HistoryItem]:
        text = (text or "").strip().lower()
        with self._lock:
            items = list(self.items)
        if not text:
            return items
        return [i for i in items if text in i.title.lower() or text in i.uploader.lower()]
