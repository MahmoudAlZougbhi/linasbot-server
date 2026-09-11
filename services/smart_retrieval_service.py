"""DEAD legacy title SequenceMatcher retrieval.

Not part of Customer Brain. Importing callables raises so this cannot
accidentally become the production retrieve path.
"""

from __future__ import annotations

from typing import Any

DEAD_FOR_CUSTOMER_BRAIN = True
_DEAD_MSG = (
    "smart_retrieval_service is DEAD for Customer Brain. "
    "Use services.customer_ai.retrieve hybrid/lexical instead."
)


def _dead(*_a: Any, **_k: Any) -> Any:
    raise RuntimeError(_DEAD_MSG)


invalidate_titles_cache = _dead
select_relevant_files = _dead
get_smart_context = _dead
build_retrieval_prompt = _dead
