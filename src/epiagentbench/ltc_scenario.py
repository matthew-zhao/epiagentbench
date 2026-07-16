"""Public scientific choices supplied by the LTC norovirus scenario pack."""

from __future__ import annotations

from typing import Any


_LTC_NOROVIRUS_HYPOTHESIS_OPTIONS = (
    (
        "propagated",
        "Cases primarily arise through person-to-person transmission within "
        "the long-term-care facility.",
        True,
    ),
    (
        "common_source",
        "Cases primarily share one contaminated source or environmental "
        "exposure within the facility.",
        True,
    ),
    (
        "repeated_introduction",
        "Cases primarily reflect multiple independent introductions into the "
        "facility rather than one internal transmission chain.",
        True,
    ),
    (
        "reporting_artifact",
        "The alert is primarily caused by duplicated, mislinked, or delayed "
        "records rather than a matching cluster of biological cases.",
        True,
    ),
    (
        "sporadic_background",
        "Observed illnesses are unrelated sporadic background events rather "
        "than one outbreak.",
        False,
    ),
    (
        "other_or_insufficient",
        "The evidence supports another explanation or is insufficient to "
        "distinguish the listed mechanisms.",
        False,
    ),
)


def ltc_norovirus_hypothesis_catalog() -> list[dict[str, Any]]:
    """Return a new JSON-ready copy of the scenario pack's public catalog."""

    return [
        {
            "id": option_id,
            "description": description,
            "target_required": target_required,
        }
        for option_id, description, target_required in (
            _LTC_NOROVIRUS_HYPOTHESIS_OPTIONS
        )
    ]
