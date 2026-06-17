#!/usr/bin/env python3
"""G1 — Grounding / hallucination signal (LLM-class).

Segments each artifact body into atomic claims and uses the active
:func:`tools.llm_provider.get_provider` to check whether each claim is
traceable to a registered source.  Ungrounded claims are surfaced as
findings.  When no backend is configured the signal returns a single
``"skipped — no backend"`` finding and never fails.
"""

from __future__ import annotations

import re

try:
    from tools.eval import Finding
    from tools.llm_provider import get_provider
except ImportError:  # script invocation: ``tools/`` is on sys.path[0]
    from eval import Finding
    from llm_provider import get_provider


_SIGNAL_ID = "G1-grounding"
_FINDING_CLASS = "llm"

# Prompt templates used to query the backend.
_SYSTEM_PROMPT = (
    "You are a grounding verifier.  Given a single factual claim and a list "
    "of registered source titles, respond with exactly one word: "
    "'grounded' if the claim is directly supported by at least one of the "
    "sources, or 'ungrounded' otherwise."
)

_CLAIM_PROMPT_TMPL = (
    "Claim: {claim}\n\nRegistered sources:\n{sources}\n\n"
    "Is this claim grounded in the sources?"
)


def _segment_claims(body: str) -> list[str]:
    """Split *body* into a list of non-empty sentences treated as atomic claims.

    Uses a simple sentence-boundary split so the signal works without an NLP
    dependency.  Bullets and numbered-list items are also treated as claims.
    """
    # Normalise list markers to sentence punctuation for a uniform split.
    text = re.sub(r"^\s*[-*+]\s+", "", body, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Split on sentence-ending punctuation followed by whitespace.
    raw = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in raw if s.strip()]


def _source_titles(sources: dict[str, dict[str, str]]) -> str:
    """Return a bullet list of registered source titles for the prompt."""
    if not sources:
        return "(none)"
    lines = []
    for key, meta in sources.items():
        title = meta.get("title") or key
        lines.append(f"- {title}")
    return "\n".join(lines)


class _GroundingSignal:
    id: str = _SIGNAL_ID
    finding_class: str = _FINDING_CLASS

    def run(self, model) -> list[Finding]:  # type: ignore[override]
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

        source_block = _source_titles(model.sources)
        findings: list[Finding] = []

        for artifact in model.artifacts:
            claims = _segment_claims(artifact.body)
            for claim in claims:
                prompt = _CLAIM_PROMPT_TMPL.format(
                    claim=claim,
                    sources=source_block,
                )
                response = provider.complete(prompt, system=_SYSTEM_PROMPT).strip().lower()
                if "ungrounded" in response:
                    findings.append(
                        Finding(
                            signal_id=self.id,
                            finding_class=self.finding_class,
                            severity="warn",
                            implicated=[str(artifact.path)],
                            explanation=f"Ungrounded claim: {claim[:120]}",
                        )
                    )

        return findings


SIGNAL = _GroundingSignal()
