#!/usr/bin/env python3
"""G7-stability: cross-run / trajectory stability signal (LLM-class).

Compares the current text of each artifact against its prior committed version
for the same task.  The LLM provider judges whether observed differences are
*substantive* (concept-level drift that deserves a finding) or *cosmetic*
(whitespace, punctuation, trivial rephrasing that should be discounted).

When no LLM backend is configured the signal returns a single
"skipped — no backend" finding rather than failing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

try:
    from tools.eval import Finding
    from tools.eval.llm_signal import LLMSignal
except ImportError:  # script invocation with tools/ on sys.path
    from eval import Finding  # type: ignore[no-redef]
    from eval.llm_signal import LLMSignal  # type: ignore[no-redef]

_SIGNAL_ID = "G7-stability"
_FINDING_CLASS = "llm"

_SYSTEM_PROMPT = (
    "You are reviewing two versions of a knowledge-base article to decide "
    "whether the changes are SUBSTANTIVE or COSMETIC.\n\n"
    "SUBSTANTIVE: concept-level drift — added, removed, or significantly altered "
    "claims, definitions, examples, or conclusions.  These matter and should be "
    "flagged.\n\n"
    "COSMETIC: whitespace, punctuation, minor rewordings that preserve all meaning, "
    "formatting-only edits.  These should be ignored.\n\n"
    "Reply with exactly one word on the first line: SUBSTANTIVE or COSMETIC.  "
    "Then, on a new line, give a one-sentence reason."
)


def _git_show_prior(path: Path, root: Path) -> str | None:
    """Return the content of *path* at HEAD, or ``None`` when unavailable."""
    rel = path.relative_to(root)
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except FileNotFoundError:
        # git not available
        return None


class _StabilitySignal(LLMSignal):
    id: str = _SIGNAL_ID
    finding_class: str = _FINDING_CLASS

    def _run_enabled(self, model, provider) -> List[Finding]:
        findings: List[Finding] = []
        for artifact in model.artifacts:
            prior_text = _git_show_prior(artifact.path, model.root)
            if prior_text is None:
                # New file, no prior version to compare against.
                continue

            current_text = artifact.path.read_text(encoding="utf-8")
            if current_text == prior_text:
                continue

            prompt = (
                "Prior version:\n"
                "```\n"
                f"{prior_text}\n"
                "```\n\n"
                "Current version:\n"
                "```\n"
                f"{current_text}\n"
                "```\n\n"
                "Are these changes SUBSTANTIVE or COSMETIC?"
            )

            try:
                response = provider.complete(prompt, system=_SYSTEM_PROMPT)
            except Exception as exc:  # noqa: BLE001
                findings.append(
                    Finding(
                        signal_id=self.id,
                        finding_class=self.finding_class,
                        severity="warn",
                        implicated=[str(artifact.path.relative_to(model.root))],
                        explanation=f"provider error during stability check: {exc}",
                    )
                )
                continue

            first_line = response.strip().splitlines()[0].strip().upper() if response.strip() else ""
            if first_line.startswith("SUBSTANTIVE"):
                reason_lines = response.strip().splitlines()[1:]
                reason = " ".join(line.strip() for line in reason_lines if line.strip())
                findings.append(
                    Finding(
                        signal_id=self.id,
                        finding_class=self.finding_class,
                        severity="warn",
                        implicated=[str(artifact.path.relative_to(model.root))],
                        explanation=reason or "substantive drift detected relative to prior commit",
                    )
                )
            # COSMETIC → no finding (discounted)

        return findings


SIGNAL = _StabilitySignal()
