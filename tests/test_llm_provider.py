"""Tests for tools/llm_provider.py."""

import importlib
import os
import sys

import pytest

# Ensure the repo root is on sys.path so ``tools`` is importable directly.
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.llm_provider import (  # noqa: E402
    DisabledProvider,
    ModelProvider,
    ProviderDisabled,
    get_provider,
)


class TestGetProvider:
    def test_returns_disabled_by_default(self):
        provider = get_provider()
        assert provider.enabled is False

    def test_returns_model_provider_instance(self):
        provider = get_provider()
        assert isinstance(provider, ModelProvider)

    def test_still_disabled_when_env_var_set(self, monkeypatch):
        monkeypatch.setenv("LLM_WIKI_MODEL_BACKEND", "some-backend")
        provider = get_provider()
        assert provider.enabled is False


class TestDisabledProvider:
    def test_enabled_is_false(self):
        p = DisabledProvider()
        assert p.enabled is False

    def test_complete_raises_provider_disabled(self):
        p = DisabledProvider()
        with pytest.raises(ProviderDisabled):
            p.complete("hello")

    def test_complete_raises_with_system_prompt(self):
        p = DisabledProvider()
        with pytest.raises(ProviderDisabled):
            p.complete("hello", system="Be concise.")

    def test_provider_disabled_is_exception(self):
        assert issubclass(ProviderDisabled, Exception)
