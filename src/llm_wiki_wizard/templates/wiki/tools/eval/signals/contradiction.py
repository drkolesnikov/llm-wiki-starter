#!/usr/bin/env python3
"""Eval signal G3: contradiction (LLM).

Detects two kinds of disagreement via an LLM judge:

* **artifact-vs-artifact** — two knowledge-notes or source-summaries make
  incompatible factual claims.
* **artifact-vs-source** — a knowledge-note contradicts the source material
  registered for the same topic (matched by ``source`` frontmatter key).

Each finding is shaped so it maps directly onto the ``conflicted`` governance
status: ``severity="warn"`` and an explanation that surfaces the word
``conflicted``, letting a reviewer or agent act without additional policy.

When no LLM backend is configured the signal returns a single
``"skipped — no backend"`` finding rather than failing.
"""

from __future__ import annotations

from typing import List

try:
    from tools.eval import Finding
    from tools.eval.llm_signal import LLMSignal
except ImportError:  # script invocation: ``tools/`` on sys.path
    from eval import Finding  # type: ignore[no-redef]
    from eval.llm_signal import LLMSignal  # type: ignore[no-redef]

_SIGNAL_ID = "G3-contradiction"
_FINDING_CLASS = "llm"

_SYSTEM_PROMPT = (
    "You are a strict factual-consistency reviewer for an LLM research wiki. "
    "Given two text passages, respond with exactly one line: "
    "'CONTRADICTION: <brief reason>' if the passages make incompatible factual "
    "claims, or 'OK' if they are consistent or merely discuss different topics."
)


def _check_pair(provider, text_a: str, text_b: str, label_a: str, label_b: str) -> str | None:
    """Return a contradiction reason string, or ``None`` if consistent."""
    prompt = (
        f"Passage A ({label_a}):\n{text_a[:1200]}\n\n"
        f"Passage B ({label_b}):\n{text_b[:1200]}\n\n"
        "Are these passages factually contradictory?"
    )
    response = provider.complete(prompt, system=_SYSTEM_PROMPT).strip()
    if response.startswith("CONTRADICTION:"):
        return response[len("CONTRADICTION:"):].strip()
    return None


class _ContradictionSignal(LLMSignal):
    """G3 — contradiction (LLM-backed)."""

    id = _SIGNAL_ID
    finding_class = _FINDING_CLASS

    def _run_enabled(self, model, provider) -> List[Finding]:
        findings: List[Finding] = []

        # Build a list of (relative_path_str, body_text) for LLM-checkable types.
        checkable = [
            (str(a.path), a.body)
            for a in model.artifacts
            if a.frontmatter.get("artifact_type") in {"knowledge-note", "source-summary"}
        ]

        # --- artifact-vs-artifact ---
        for i, (path_a, body_a) in enumerate(checkable):
            for path_b, body_b in checkable[i + 1:]:
                reason = _check_pair(provider, body_a, body_b, path_a, path_b)
                if reason:
                    findings.append(
                        Finding(
                            signal_id=self.id,
                            finding_class=self.finding_class,
                            severity="warn",
                            implicated=[path_a, path_b],
                            explanation=(
                                f"conflicted: artifact-vs-artifact disagreement — {reason}. "
                                "Set status: conflicted and resolve before promoting."
                            ),
                        )
                    )

        # --- artifact-vs-source ---
        for artifact in model.artifacts:
            source_key = artifact.frontmatter.get("source")
            if not source_key:
                continue
            source_meta = model.sources.get(str(source_key))
            if not source_meta:
                continue
            # Use the source's description as a proxy for its content.
            source_text = source_meta.get("description") or source_meta.get("title") or ""
            if not source_text.strip():
                continue
            reason = _check_pair(
                provider,
                artifact.body,
                source_text,
                str(artifact.path),
                f"source:{source_key}",
            )
            if reason:
                findings.append(
                    Finding(
                        signal_id=self.id,
                        finding_class=self.finding_class,
                        severity="warn",
                        implicated=[str(artifact.path)],
                        explanation=(
                            f"conflicted: artifact-vs-source disagreement with "
                            f"'{source_key}' — {reason}. "
                            "Set status: conflicted and reconcile with the source."
                        ),
                    )
                )

        return findings


SIGNAL = _ContradictionSignal()
