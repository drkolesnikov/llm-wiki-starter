#!/usr/bin/env python3
"""Tests for the G5-stale evaluation signal.

All tests use injected run_date and threshold_days so they are fully
deterministic — no wall-clock dependence.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Minimal stubs — no filesystem I/O required
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Artifact:
    """Stub mimicking tools.wiki_model.Artifact."""

    path: Path
    frontmatter: dict = field(default_factory=dict)
    body: str = ""


@dataclass(frozen=True)
class _RepoModel:
    """Stub mimicking tools.wiki_model.RepoModel."""

    root: Path = Path("/fake/root")
    artifacts: list = field(default_factory=list)
    sources: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Import the signal under test
# ---------------------------------------------------------------------------

from tools.eval.signals.stale import SIGNAL, _StaleSignal  # noqa: E402


class StaleSignalMetaTests(unittest.TestCase):
    """Basic protocol-compliance checks."""

    def test_id(self):
        self.assertEqual("G5-stale", SIGNAL.id)

    def test_finding_class(self):
        self.assertEqual("deterministic", SIGNAL.finding_class)

    def test_run_returns_list(self):
        model = _RepoModel()
        result = SIGNAL.run(model)
        self.assertIsInstance(result, list)


class StaleSignalFlaggedTests(unittest.TestCase):
    """Artifacts older than the threshold must be flagged."""

    def _signal(self, *, run_date: date, threshold_days: int) -> _StaleSignal:
        """Return a fresh _StaleSignal with injected run_date and threshold."""
        sig = _StaleSignal()
        sig.run_date = run_date
        sig.threshold_days = threshold_days
        return sig

    def test_artifact_older_than_threshold_is_flagged(self):
        run_date = date(2024, 6, 1)
        threshold_days = 365
        # 500 days before run_date — clearly stale
        updated = date(2023, 1, 17)  # 500 days before 2024-06-01

        artifact = _Artifact(
            path=Path("notes/old-note.md"),
            frontmatter={"updated": updated.isoformat()},
        )
        model = _RepoModel(artifacts=[artifact])
        sig = self._signal(run_date=run_date, threshold_days=threshold_days)
        findings = sig.run(model)

        self.assertEqual(1, len(findings))
        finding = findings[0]
        self.assertEqual("G5-stale", finding.signal_id)
        self.assertEqual("deterministic", finding.finding_class)
        self.assertEqual("warn", finding.severity)
        self.assertIn(str(artifact.path), finding.implicated)
        self.assertIn(updated.isoformat(), finding.explanation)

    def test_artifact_within_threshold_is_not_flagged(self):
        run_date = date(2024, 6, 1)
        threshold_days = 365
        # 30 days before run_date — within threshold
        updated = date(2024, 5, 2)

        artifact = _Artifact(
            path=Path("notes/fresh-note.md"),
            frontmatter={"updated": updated.isoformat()},
        )
        model = _RepoModel(artifacts=[artifact])
        sig = self._signal(run_date=run_date, threshold_days=threshold_days)
        findings = sig.run(model)

        self.assertEqual(0, len(findings))

    def test_exactly_at_threshold_boundary_is_not_flagged(self):
        """An artifact updated exactly threshold_days ago is NOT stale (strict < cutoff)."""
        run_date = date(2024, 6, 1)
        threshold_days = 365
        # exactly threshold_days before run_date
        from datetime import timedelta
        updated = run_date - timedelta(days=threshold_days)

        artifact = _Artifact(
            path=Path("notes/boundary-note.md"),
            frontmatter={"updated": updated.isoformat()},
        )
        model = _RepoModel(artifacts=[artifact])
        sig = self._signal(run_date=run_date, threshold_days=threshold_days)
        findings = sig.run(model)

        # Exactly at the boundary: not strictly older, so no finding.
        self.assertEqual(0, len(findings))

    def test_one_day_past_boundary_is_flagged(self):
        """One day past the threshold means the artifact IS stale."""
        from datetime import timedelta
        run_date = date(2024, 6, 1)
        threshold_days = 365
        updated = run_date - timedelta(days=threshold_days + 1)

        artifact = _Artifact(
            path=Path("notes/just-over.md"),
            frontmatter={"updated": updated.isoformat()},
        )
        model = _RepoModel(artifacts=[artifact])
        sig = self._signal(run_date=run_date, threshold_days=threshold_days)
        findings = sig.run(model)

        self.assertEqual(1, len(findings))

    def test_custom_threshold_respected(self):
        """A shorter custom threshold flags more artifacts."""
        run_date = date(2024, 6, 1)
        threshold_days = 30
        # 60 days ago — stale under 30-day threshold but fresh under 365-day
        updated = date(2024, 4, 2)

        artifact = _Artifact(
            path=Path("notes/moderate-note.md"),
            frontmatter={"updated": updated.isoformat()},
        )
        model = _RepoModel(artifacts=[artifact])
        sig = self._signal(run_date=run_date, threshold_days=threshold_days)
        findings = sig.run(model)

        self.assertEqual(1, len(findings))

    def test_custom_run_date_shifts_staleness(self):
        """Injecting a different run_date changes which artifacts are stale."""
        threshold_days = 365
        updated = date(2023, 1, 1)
        artifact = _Artifact(
            path=Path("notes/shifting.md"),
            frontmatter={"updated": updated.isoformat()},
        )
        model = _RepoModel(artifacts=[artifact])

        # Run-date far in the future — stale
        sig_future = self._signal(run_date=date(2025, 1, 1), threshold_days=threshold_days)
        self.assertEqual(1, len(sig_future.run(model)))

        # Run-date only 100 days after updated — not stale
        sig_near = self._signal(run_date=date(2023, 4, 11), threshold_days=threshold_days)
        self.assertEqual(0, len(sig_near.run(model)))

    def test_body_date_triggers_finding(self):
        """An ISO-8601 date in the artifact body (cited source) can trigger staleness."""
        run_date = date(2024, 6, 1)
        threshold_days = 365
        # No frontmatter date; stale date embedded in body text
        body = "Source retrieved on 2022-01-15 confirms the claim."
        artifact = _Artifact(
            path=Path("notes/body-date.md"),
            frontmatter={},
            body=body,
        )
        model = _RepoModel(artifacts=[artifact])
        sig = self._signal(run_date=run_date, threshold_days=threshold_days)
        findings = sig.run(model)

        self.assertEqual(1, len(findings))
        self.assertIn("2022-01-15", findings[0].explanation)

    def test_body_date_within_threshold_no_finding(self):
        """A fresh body date does not trigger a finding."""
        run_date = date(2024, 6, 1)
        threshold_days = 365
        body = "Source retrieved on 2024-05-15 confirms the claim."
        artifact = _Artifact(
            path=Path("notes/fresh-body.md"),
            frontmatter={},
            body=body,
        )
        model = _RepoModel(artifacts=[artifact])
        sig = self._signal(run_date=run_date, threshold_days=threshold_days)
        findings = sig.run(model)

        self.assertEqual(0, len(findings))

    def test_no_dates_produces_no_finding(self):
        """An artifact with no parseable dates produces no finding."""
        artifact = _Artifact(
            path=Path("notes/no-date.md"),
            frontmatter={"title": "No date here"},
            body="No date in this body either.",
        )
        model = _RepoModel(artifacts=[artifact])
        sig = self._signal(run_date=date(2024, 6, 1), threshold_days=365)
        findings = sig.run(model)

        self.assertEqual(0, len(findings))

    def test_multiple_artifacts_only_stale_flagged(self):
        """Mix of stale and fresh artifacts — only the stale one is flagged."""
        run_date = date(2024, 6, 1)
        threshold_days = 365

        stale_artifact = _Artifact(
            path=Path("notes/stale.md"),
            frontmatter={"updated": "2022-01-01"},
        )
        fresh_artifact = _Artifact(
            path=Path("notes/fresh.md"),
            frontmatter={"updated": "2024-05-20"},
        )
        model = _RepoModel(artifacts=[stale_artifact, fresh_artifact])
        sig = self._signal(run_date=run_date, threshold_days=threshold_days)
        findings = sig.run(model)

        self.assertEqual(1, len(findings))
        self.assertIn(str(stale_artifact.path), findings[0].implicated)

    def test_finding_reported_by_discovery(self):
        """The signal is discovered by the auto-discovery mechanism."""
        from tools.eval import discover_signals
        discovered_ids = [sig.id for _, sig in discover_signals()]
        self.assertIn("G5-stale", discovered_ids)


if __name__ == "__main__":
    unittest.main()
