"""Stable local project scope; display-name changes cannot reset payout coverage."""
from __future__ import annotations

import hashlib
import re
import unicodedata

LEGACY = re.compile(r"legacy-[0-9a-f]{64}\Z")
NEW = re.compile(r"project-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


def legacy_id(name):
    normalized = unicodedata.normalize("NFC", name.casefold())
    return "legacy-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def resolve(source):
    value = source.get("project_id")
    if value is None:
        return legacy_id(source["project"])
    if not isinstance(value, str) or not (LEGACY.fullmatch(value) or NEW.fullmatch(value)):
        raise ValueError("Project identity is invalid. Reopen the saved statement or explicitly start a new project.")
    return value


def is_new(value):
    return isinstance(value, str) and NEW.fullmatch(value) is not None
