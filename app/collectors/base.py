from __future__ import annotations
import datetime as _dt
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawItem:
    title: str = ""
    text: str = ""
    url: Optional[str] = None
    html: Optional[str] = None
    published_at: Optional[_dt.datetime] = None
    extra: dict = field(default_factory=dict)
