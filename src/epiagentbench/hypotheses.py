"""Public hypothesis-catalog validation shared by scenario packs and scoring.

The kernel deliberately does not define the available scientific answers.  A
scenario pack publishes those answers in its episode manifest and the trusted
scorer uses the exact same public catalog to validate the final distribution.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


HYPOTHESIS_CATALOG_KEYS = frozenset(
    {"id", "description", "target_required"}
)
_CATALOG_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def normalize_hypothesis_catalog(value: Any) -> tuple[dict[str, Any], ...]:
    """Validate and detach one public, scenario-defined answer catalog.

    Exact schemas make malformed or accidentally augmented evaluator data fail
    closed.  Descriptions are public task instructions, never oracle labels.
    ``target_required`` is also an exact target rule: true requires a non-null
    public target and false requires null in the submitted option.
    """

    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not 2 <= len(value) <= 32
    ):
        raise ValueError("hypothesis catalog must contain 2 to 32 options")

    normalized: list[dict[str, Any]] = []
    option_ids: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping) or set(raw) != HYPOTHESIS_CATALOG_KEYS:
            raise ValueError(f"invalid hypothesis catalog option {index}")
        option_id = raw["id"]
        description = raw["description"]
        target_required = raw["target_required"]
        if not isinstance(option_id, str) or not _CATALOG_ID.fullmatch(option_id):
            raise ValueError(f"invalid hypothesis catalog id {index}")
        if option_id in option_ids:
            raise ValueError("duplicate hypothesis catalog id")
        if (
            not isinstance(description, str)
            or not description.strip()
            or len(description) > 512
        ):
            raise ValueError(f"invalid hypothesis catalog description {index}")
        if type(target_required) is not bool:
            raise ValueError(f"invalid hypothesis target rule {index}")
        option_ids.add(option_id)
        normalized.append(
            {
                "id": option_id,
                "description": description,
                "target_required": target_required,
            }
        )
    return tuple(normalized)


def hypothesis_catalog_ids(value: Any) -> tuple[str, ...]:
    """Return catalog IDs after applying the strict public schema."""

    return tuple(
        option["id"] for option in normalize_hypothesis_catalog(value)
    )
