"""Monkey-patch LangChain to preserve reasoning content from any API format.

``_convert_delta_to_message_chunk`` in langchain-openai only copies
``function_call`` into ``additional_kwargs`` from the delta dict. However,
OpenAI-compatible reasoning APIs (DeepSeek, newer OpenAI models, etc.) send
reasoning content in proprietary fields that are silently dropped.

Known field names (all normalized to ``additional_kwargs["reasoning_content"]``):

  ====================  ======  ===========================================
  Field                 Level   Providers
  ====================  ======  ===========================================
  ``reasoning_content`` choice  DeepSeek (full accumulated text per chunk)
  ``reasoning``         delta   OpenAI o-series, Gemini compat (delta text)
  ``reasoning_details`` delta   Same providers, structured array per delta
  ====================  ======  ===========================================

This module patches two private functions on ``BaseChatOpenAI``:
1. ``_convert_chunk_to_generation_chunk`` — extracts ``reasoning_content``
   from the choice dict (choice-level fields).
2. ``_convert_delta_to_message_chunk`` — extracts ``reasoning`` and
   ``reasoning_details`` from the delta dict (delta-level fields).

**Version drift risk.** Both are private implementation details. Bumping
``langchain-openai`` may silently break the patch. Pin ``langchain-openai``
in ``pyproject.toml`` and update the ``PATCHED_METHODS`` set when upgrading.
"""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from typing import Any as _Any

import langchain_openai.chat_models.base as _lc_openai_base

# Used by the version-drift safety check on first import.
PATCHED_METHODS = {
    "BaseChatOpenAI._convert_chunk_to_generation_chunk",
    "_convert_delta_to_message_chunk",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_reasoning_details(
    raw: _Any,
) -> str | None:
    """Extract delta text from a ``reasoning_details`` array.

    The array format is::

        [{"type": "reasoning.text", "text": " delta text here "}, ...]

    Returns the concatenation of all ``text`` fields, or ``None`` if the
    input isn't a list with at least one valid entry.
    """
    if not isinstance(raw, list) or not raw:
        return None
    parts: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            text = entry.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    return "".join(parts) if parts else None


def _gather_reasoning_delta(_dict: _Mapping[str, _Any]) -> str | None:
    """Try every known delta-level reasoning field, returning the first hit."""
    for key in ("reasoning_content", "reasoning"):
        val = _dict.get(key)
        if val is not None and isinstance(val, str) and val:
            return val
    # Fall through to the structured array format
    return _extract_reasoning_details(_dict.get("reasoning_details"))


# ---------------------------------------------------------------------------
# Patch 1: _convert_delta_to_message_chunk (delta-level defense in depth)
# ---------------------------------------------------------------------------

_orig_convert_delta = _lc_openai_base._convert_delta_to_message_chunk


def _patched_convert_delta(
    _dict: _Mapping[str, _Any],
    default_class: type,
) -> _Any:
    reasoning = _gather_reasoning_delta(_dict)
    result = _orig_convert_delta(_dict, default_class)
    if reasoning is not None and hasattr(result, "additional_kwargs"):
        # Normalize to reasoning_content so StreamEventHandler can find it
        result.additional_kwargs["reasoning_content"] = reasoning
    return result


_lc_openai_base._convert_delta_to_message_chunk = _patched_convert_delta

# ---------------------------------------------------------------------------
# Patch 2: BaseChatOpenAI._convert_chunk_to_generation_chunk (choice-level)
# ---------------------------------------------------------------------------
# This is the primary fix for DeepSeek-style APIs where reasoning_content
# lives at the choice level, not inside delta::
#
#     {"choices": [{"delta": {"content": ""}, "reasoning_content": "..."}], ...}

_orig_convert_chunk = _lc_openai_base.BaseChatOpenAI._convert_chunk_to_generation_chunk  # type: ignore[attr-defined]


def _patched_convert_chunk(
    self: _Any,
    chunk: dict,
    default_chunk_class: type,
    base_generation_info: dict | None,
) -> _Any:
    # Grab reasoning_content from the choice before calling the original
    reasoning: str | None = None
    choices = chunk.get("choices", [])
    if choices:
        reasoning = choices[0].get("reasoning_content")

    result = _orig_convert_chunk(self, chunk, default_chunk_class, base_generation_info)

    if reasoning is not None and result is not None:
        msg = result.message
        if hasattr(msg, "additional_kwargs"):
            msg.additional_kwargs["reasoning_content"] = reasoning

    return result


_lc_openai_base.BaseChatOpenAI._convert_chunk_to_generation_chunk = _patched_convert_chunk  # type: ignore[attr-defined]
