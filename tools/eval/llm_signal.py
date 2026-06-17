#!/usr/bin/env python3
"""Base class for LLM-backed eval signals.

:class:`LLMSignal` implements the disabled-backend guard in one place via the
template-method pattern.  Concrete signals inherit from it and implement only
:meth:`_run_enabled`, which receives the resolved provider and the repo model.

The single ``"skipped — no backend"`` :class:`tools.eval.Finding` lives here;
no copy exists in individual signal modules.
"""

from __future__ import annotations

from typing import List

try:
    from tools.eval import Finding
    from tools.llm_provider import get_provider
except ImportError:  # script invocation: ``tools/`` is on sys.path[0]
    from eval import Finding  # type: ignore[no-redef]
    from llm_provider import get_provider  # type: ignore[no-redef]


class LLMSignal:
    """Template-method base for LLM-backed signals.

    Subclasses **must** define:

    - ``id`` — the signal identifier string (e.g. ``"G1-grounding"``).
    - ``finding_class`` — the finding-class string (e.g. ``"llm"``).
    - :meth:`_run_enabled` — the evaluation logic, called only when the
      provider is enabled.

    Subclasses **must not** override :meth:`run`.
    """

    id: str
    finding_class: str

    # ------------------------------------------------------------------
    # Public API (do not override)
    # ------------------------------------------------------------------

    def run(self, model) -> List[Finding]:  # noqa: ANN001
        """Run the signal, handling the disabled-backend guard.

        When the active provider reports ``enabled=False``, returns a single
        ``"skipped — no backend"`` finding with ``severity="info"`` and does
        not call :meth:`_run_enabled`.

        Parameters
        ----------
        model:
            A :class:`tools.wiki_model.RepoModel` instance.

        Returns
        -------
        list[Finding]
            Zero or more findings, or the single skipped finding when no
            backend is available.
        """
        provider = get_provider()
        if not provider.enabled:
            return [
                Finding(
                    signal_id=self.id,
                    finding_class=self.finding_class,
                    severity="info",
                    implicated=[],
                    explanation="skipped — no backend",
                )
            ]
        return self._run_enabled(model, provider)

    # ------------------------------------------------------------------
    # Override point for subclasses
    # ------------------------------------------------------------------

    def _run_enabled(self, model, provider) -> List[Finding]:  # noqa: ANN001
        """Run the signal logic when the backend is available.

        Parameters
        ----------
        model:
            A :class:`tools.wiki_model.RepoModel` instance.
        provider:
            An enabled :class:`tools.llm_provider.ModelProvider`.

        Returns
        -------
        list[Finding]
            Signal findings (may be empty).
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _run_enabled(model, provider)"
        )
