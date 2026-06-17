"""Pluggable model-provider interface for llm-wiki tools.

Usage::

    from tools.llm_provider import get_provider, ProviderDisabled

    provider = get_provider()
    if provider.enabled:
        result = provider.complete("Summarise this article.", system="Be concise.")
    else:
        # LLM work is skipped when no backend is configured
        result = None

Environment variables
---------------------
LLM_WIKI_MODEL_BACKEND
    When set, signals that a backend is desired.  Wiring an actual backend is
    out of scope for this module — ``get_provider()`` still returns a
    ``DisabledProvider`` until a real implementation is registered.
"""

from __future__ import annotations

import abc
import os


class ProviderDisabled(Exception):
    """Raised when ``complete()`` is called on a disabled provider."""


class ModelProvider(abc.ABC):
    """Abstract base class for model providers."""

    #: ``True`` when the provider can actually process requests.
    enabled: bool = False

    @abc.abstractmethod
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Return the model's completion for *prompt*.

        Parameters
        ----------
        prompt:
            The user-turn text sent to the model.
        system:
            Optional system prompt.

        Returns
        -------
        str
            The model's text response.

        Raises
        ------
        ProviderDisabled
            When the provider is not enabled.
        """


class DisabledProvider(ModelProvider):
    """Default no-op provider used when no backend is configured.

    Callers should check ``provider.enabled`` before calling ``complete()``
    to avoid the ``ProviderDisabled`` exception.
    """

    enabled: bool = False

    def complete(self, prompt: str, *, system: str | None = None) -> str:  # noqa: ARG002
        raise ProviderDisabled(
            "No LLM backend is configured.  Set LLM_WIKI_MODEL_BACKEND and "
            "wire a real ModelProvider to enable LLM features."
        )


def get_provider() -> ModelProvider:
    """Return the active ``ModelProvider``.

    Currently always returns a ``DisabledProvider``.  When
    ``LLM_WIKI_MODEL_BACKEND`` is set the intent to use a backend is
    acknowledged, but wiring a real implementation is out of scope for this
    module.

    Returns
    -------
    ModelProvider
        A provider instance.  Check ``.enabled`` before calling
        ``.complete()``.
    """
    # Acknowledge the env var without wiring a real backend yet.
    _backend = os.environ.get("LLM_WIKI_MODEL_BACKEND")  # noqa: F841 — reserved for future use
    return DisabledProvider()
