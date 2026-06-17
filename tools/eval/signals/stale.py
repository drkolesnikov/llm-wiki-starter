#!/usr/bin/env python3
"""G5-stale — deterministic staleness signal.

Flags artifacts whose ``updated`` frontmatter date (or dates found in their
cited sources) exceeds a configurable age threshold, evaluated against an
**injected** run-date. No wall-clock dependence; the signal is fully
deterministic when tested with explicit dates.

Configuration is via the signal's attributes so tests can override them:

    from tools.eval.signals.stale import SIGNAL
    SIGNAL.threshold_days = 180
    SIGNAL.run_date = date(2024, 1, 1)

The defaults applied when neither is set:

- ``threshold_days`` defaults to ``365`` (one year).
- ``run_date`` defaults to ``None``, which means the signal reads
  ``date.today()`` **at call time**. Override in tests to keep them
  deterministic.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import List, Optional

try:
    from tools.eval import Finding
except ImportError:
    from eval import Finding  # type: ignore[no-reuse-source]

# ISO-8601 date pattern used when scanning artifact bodies for source dates.
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _parse_date(value: object) -> Optional[date]:
    """Return a :class:`~datetime.date` for *value*, or ``None`` if unparseable."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


class _StaleSignal:
    """Deterministic staleness signal (catalog id G5)."""

    id: str = "G5-stale"
    finding_class: str = "deterministic"

    #: Maximum age in days before an artifact is considered stale.
    #: Injectable so tests never depend on the wall clock.
    threshold_days: int = 365

    #: The date used as "today" when computing age.
    #: ``None`` means use ``date.today()`` at call time; set explicitly in tests.
    run_date: Optional[date] = None

    def run(self, model) -> List[Finding]:
        """Inspect every artifact in *model* and return staleness findings.

        An artifact is flagged when either:

        - its ``updated`` frontmatter field is present, parseable, and older
          than ``threshold_days`` relative to ``run_date``; or
        - any ISO-8601 date found in its body (from inline source citations)
          is older than ``threshold_days`` relative to ``run_date``.

        Artifacts with no parseable dates produce no finding.
        """

        effective_run_date: date = self.run_date if self.run_date is not None else date.today()
        cutoff: date = effective_run_date - timedelta(days=self.threshold_days)

        findings: List[Finding] = []
        for artifact in model.artifacts:
            stale_dates: list[date] = []
            reasons: list[str] = []

            # Check the ``updated`` frontmatter field.
            updated_raw = artifact.frontmatter.get("updated")
            if updated_raw is not None:
                updated = _parse_date(updated_raw)
                if updated is not None and updated < cutoff:
                    stale_dates.append(updated)
                    reasons.append(f"updated={updated.isoformat()}")

            # Scan the artifact body for ISO-8601 dates (source citations, etc.).
            body_dates = [
                d
                for raw in _DATE_RE.findall(artifact.body)
                if (d := _parse_date(raw)) is not None and d < cutoff
            ]
            for d in body_dates:
                if d not in stale_dates:
                    stale_dates.append(d)
                    reasons.append(f"body-date={d.isoformat()}")

            if stale_dates:
                oldest = min(stale_dates)
                age_days = (effective_run_date - oldest).days
                findings.append(
                    Finding(
                        signal_id=self.id,
                        finding_class=self.finding_class,
                        severity="warn",
                        implicated=[str(artifact.path)],
                        explanation=(
                            f"Stale artifact: oldest date {oldest.isoformat()} "
                            f"is {age_days} day(s) old "
                            f"(threshold {self.threshold_days}). "
                            f"Dates found: {'; '.join(reasons)}."
                        ),
                    )
                )

        return findings


SIGNAL = _StaleSignal()
