"""Monkey-patch LangChain's delta-to-message converter to preserve reasoning_content.

``_convert_delta_to_message_chunk`` in langchain-openai only copies
``function_call`` into ``additional_kwargs``. OpenAI-compatible reasoning
APIs send ``reasoning_content`` in the delta dict, which is silently
dropped. Our stream handler checks
``additional_kwargs.get("reasoning_content")`` and never sees it.
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from typing import Any as _Any

import langchain_openai.chat_models.base as _lc_openai_base

_orig_convert = _lc_openai_base._convert_delta_to_message_chunk


def _patched_convert_delta(
    _dict: _Mapping[str, _Any],
    default_class: type,
) -> _Any:
    result = _orig_convert(_dict, default_class)
    reasoning = _dict.get("reasoning_content")
    if reasoning is not None and hasattr(result, "additional_kwargs"):
        result.additional_kwargs["reasoning_content"] = str(reasoning)
    return result


_lc_openai_base._convert_delta_to_message_chunk = _patched_convert_delta
