"""Stable concept identity.

A concept's identity is its *name*, not the file it was found in — the
same concept resurfacing in a different file must map to the same store
key.  :func:`concept_slug` derives a stable slug from the name;
:func:`normalize_concept_name` provides the shared canonical form used
for comparisons and cache lookups.
"""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_concept_name(name: str) -> str:
    """Canonical form of a concept name for identity comparisons.

    Unicode-normalized, lowercased, whitespace collapsed.
    """
    if not isinstance(name, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.lower().split())


def concept_slug(name: str) -> str:
    """Stable slug for a concept name — the store's identity key.

    Alphanumeric characters are kept, every other run collapses to a
    single hyphen: ``"useEffect"`` → ``useeffect``,
    ``"Classes / OOP"`` → ``classes-oop``, ``"__init__ (Constructor)"``
    → ``init-constructor``.  Deterministic across processes and runs.
    """
    normalized = normalize_concept_name(name)
    return _NON_ALNUM.sub("-", normalized).strip("-")
