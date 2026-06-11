"""Monkey-patch LangChain to preserve reasoning_content from the API response.

``_convert_delta_to_message_chunk`` in langchain-openai only copies
``function_call`` into ``additional_kwargs`` from the delta dict. However,
OpenAI-compatible reasoning APIs (DeepSeek, etc.) send ``reasoning_content``
at the **choice** level, not inside delta::

    {"choices": [{"delta": {"content": ""}, "reasoning_content": "..."}], ...}

LangChain's ``_convert_chunk_to_generation_chunk`` only passes
``choice["delta"]`` to ``_convert_delta_to_message_chunk``, so
reasoning_content is silently dropped before our patch ever sees it.

This module patches both:
1. ``BaseChatOpenAI._convert_chunk_to_generation_chunk`` — extracts
   ``reasoning_content`` from the choice dict and puts it into
   ``additional_kwargs`` on the ``AIMessageChunk``.
2. ``_convert_delta_to_message_chunk`` — defense in depth for providers
   that do put it in the delta.
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from typing import Any as _Any

import langchain_openai.chat_models.base as _lc_openai_base

# ── Patch 1: _convert_delta_to_message_chunk (defense in depth) ──────

_orig_convert_delta = _lc_openai_base._convert_delta_to_message_chunk


def _patched_convert_delta(
    _dict: _Mapping[str, _Any],
    default_class: type,
) -> _Any:
    result = _orig_convert_delta(_dict, default_class)
    reasoning = _dict.get("reasoning_content")
    if reasoning is not None and hasattr(result, "additional_kwargs"):
        result.additional_kwargs["reasoning_content"] = str(reasoning)
    return result


_lc_openai_base._convert_delta_to_message_chunk = _patched_convert_delta

# ── Patch 2: BaseChatOpenAI._convert_chunk_to_generation_chunk ───────
# This is the real fix — reasoning_content lives at the choice level.

_orig_convert_chunk = _lc_openai_base.BaseChatOpenAI._convert_chunk_to_generation_chunk  # type: ignore[attr-defined]


def _patched_convert_chunk(
    self: _Any,
    chunk: dict,
    default_chunk_class: type,
    base_generation_info: dict | None,
) -> _Any:
    # Grab reasoning_content from the choice before calling the original
    reasoning_content: str | None = None
    choices = chunk.get("choices", [])
    if choices:
        reasoning_content = choices[0].get("reasoning_content")

    result = _orig_convert_chunk(self, chunk, default_chunk_class, base_generation_info)

    if reasoning_content is not None and result is not None:
        msg = result.message
        if hasattr(msg, "additional_kwargs"):
            msg.additional_kwargs["reasoning_content"] = str(reasoning_content)

    return result


_lc_openai_base.BaseChatOpenAI._convert_chunk_to_generation_chunk = _patched_convert_chunk  # type: ignore[attr-defined]
