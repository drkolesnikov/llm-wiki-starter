"""Tests for tools/llm_provider.py."""

import os
import sys
import unittest
from unittest import mock

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


class TestGetProvider(unittest.TestCase):
    def test_returns_disabled_by_default(self):
        self.assertFalse(get_provider().enabled)

    def test_returns_model_provider_instance(self):
        self.assertIsInstance(get_provider(), ModelProvider)

    def test_still_disabled_when_env_var_set(self):
        with mock.patch.dict(os.environ, {"LLM_WIKI_MODEL_BACKEND": "some-backend"}):
            self.assertFalse(get_provider().enabled)


class TestDisabledProvider(unittest.TestCase):
    def test_enabled_is_false(self):
        self.assertFalse(DisabledProvider().enabled)

    def test_complete_raises_provider_disabled(self):
        with self.assertRaises(ProviderDisabled):
            DisabledProvider().complete("hello")

    def test_complete_raises_with_system_prompt(self):
        with self.assertRaises(ProviderDisabled):
            DisabledProvider().complete("hello", system="Be concise.")

    def test_provider_disabled_is_exception(self):
        self.assertTrue(issubclass(ProviderDisabled, Exception))


if __name__ == "__main__":
    unittest.main()
