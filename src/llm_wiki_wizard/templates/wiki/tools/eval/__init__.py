#!/usr/bin/env python3
"""Evaluation framework for the LLM wiki starter repository.

This package provides the *signal* interface and the auto-discovered suite the
eight wiki-health signal slices (issue #20) build on. The contract mirrors the
structural-check registry in :mod:`tools.checks`: each signal is **add-a-file**.
Drop a ``*.py`` module exposing a module-level ``SIGNAL`` object into
``tools/eval/signals/`` and it registers with no edit to this module.

Building blocks
---------------
:class:`Finding`
    An immutable evaluation result: which signal raised it, whether it came
    from a deterministic rule or an LLM judge, its severity, the artifacts it
    implicates, and a human-readable explanation.
:class:`Signal`
    A :class:`typing.Protocol` describing a runnable signal: an ``id``, a
    ``finding_class`` (``"deterministic"`` or ``"llm"``), and a
    ``run(model) -> list[Finding]`` method where ``model`` is the
    :class:`tools.wiki_model.RepoModel` parsed once per run.
:func:`discover_signals`
    Scans ``tools/eval/signals/*.py`` for a module-level ``SIGNAL`` object in
    sorted filename order. No central list to edit.
:func:`run_suite`
    Runs every discovered signal (or a selected subset) against a ``RepoModel``
    and returns the accumulated findings.
:func:`render_report`
    Renders findings as a ``(markdown, machine_dict)`` pair (the G8 report
    skeleton): a Markdown form for humans and a machine-readable dict for tools.

Findings are **advisory**. They surface under the validator's advisory-health
tier and never change its exit status.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional, Protocol, Sequence, Tuple, runtime_checkable

try:  # script invocation: ``tools/`` is on sys.path[0]
    from _registry import discover_modules
except ImportError:  # imported as ``tools.eval``
    from tools._registry import discover_modules


#: A finding either comes from a deterministic rule or an LLM judge.
FindingClass = str  # one of {"deterministic", "llm"}

#: Allowed values for ``Finding.finding_class``.
FINDING_CLASSES = ("deterministic", "llm")


@dataclass(frozen=True)
class Finding:
    """A single advisory evaluation result.

    Parameters
    ----------
    signal_id:
        The ``id`` of the signal that produced this finding.
    finding_class:
        ``"deterministic"`` for rule-based signals or ``"llm"`` for signals
        backed by a model provider.
    severity:
        A free-form severity label (e.g. ``"info"``, ``"warn"``). Eval findings
        are advisory regardless of severity.
    implicated:
        Repository-relative paths (or other identifiers) the finding points at.
    explanation:
        A human-readable description of what was found.
    """

    signal_id: str
    finding_class: FindingClass
    severity: str
    implicated: List[str] = field(default_factory=list)
    explanation: str = ""

    def as_dict(self) -> dict:
        """Return a JSON-serialisable view of this finding."""

        return {
            "signal_id": self.signal_id,
            "finding_class": self.finding_class,
            "severity": self.severity,
            "implicated": list(self.implicated),
            "explanation": self.explanation,
        }


@runtime_checkable
class Signal(Protocol):
    """A runnable evaluation signal.

    Implementations expose an ``id`` (stable identifier used in findings and
    selection), a ``finding_class`` (``"deterministic"`` or ``"llm"``), and a
    ``run`` method that inspects a :class:`tools.wiki_model.RepoModel` and
    returns zero or more :class:`Finding` objects.

    LLM-class signals obtain their backend via
    :func:`tools.llm_provider.get_provider` and, when no backend is configured,
    return a single ``"skipped — no backend"`` finding rather than failing.
    """

    id: str
    finding_class: FindingClass

    def run(self, model) -> List[Finding]:  # pragma: no cover - protocol stub
        ...


# A discovered signal: (module_name, signal_object).
DiscoveredSignal = Tuple[str, Signal]


def _signals_package():
    """Import and return the ``signals`` subpackage.

    Resolved relative to this package's own ``__name__`` so the same code path
    works whether we were imported as ``tools.eval`` (package) or ``eval``
    (script invocation with ``tools/`` on ``sys.path``).
    """

    return importlib.import_module(f"{__name__}.signals")


def discover_signals() -> List[DiscoveredSignal]:
    """Return ``(name, SIGNAL)`` pairs for every signal module, sorted by name.

    Discovery is deterministic: modules under ``tools/eval/signals/`` are
    imported in ascending filename order and only those exposing a module-level
    ``SIGNAL`` object are included. Private modules (leading underscore) are
    ignored. An empty ``signals`` directory yields an empty list.
    """

    signals_pkg = _signals_package()
    return discover_modules(signals_pkg.__path__, signals_pkg.__name__, "SIGNAL", sort=True)


def run_suite(model, *, selected: Sequence[str] | None = None) -> List[Finding]:
    """Run discovered signals against ``model`` and return their findings.

    Parameters
    ----------
    model:
        The :class:`tools.wiki_model.RepoModel` to evaluate.
    selected:
        Optional collection of signal ids. When provided, only signals whose
        ``id`` is in this collection run; others are skipped. When ``None``
        (the default), every discovered signal runs.

    Signals run in deterministic (sorted filename) order so accumulated
    findings are stable across runs.
    """

    selected_set = set(selected) if selected is not None else None
    findings: List[Finding] = []
    for _name, signal in discover_signals():
        if selected_set is not None and signal.id not in selected_set:
            continue
        findings.extend(signal.run(model))
    return findings


def render_report(findings: Sequence[Finding]) -> Tuple[str, dict]:
    """Render ``findings`` as a ``(markdown, machine_dict)`` pair.

    The Markdown form is a human-readable report; the machine dict is a
    JSON-serialisable summary (the G8 report skeleton) keyed by ``findings``
    plus a per-class ``counts`` breakdown. With no findings the Markdown notes
    "No findings." and the dict reports zero counts.
    """

    findings = list(findings)
    counts: dict[str, int] = {cls: 0 for cls in FINDING_CLASSES}
    for finding in findings:
        counts[finding.finding_class] = counts.get(finding.finding_class, 0) + 1

    lines = ["# Evaluation report", ""]
    if not findings:
        lines.append("No findings.")
    else:
        lines.append(f"{len(findings)} finding(s).")
        lines.append("")
        for finding in findings:
            implicated = ", ".join(finding.implicated) if finding.implicated else "—"
            lines.append(
                f"- **{finding.signal_id}** "
                f"[{finding.finding_class}/{finding.severity}] "
                f"({implicated}): {finding.explanation}"
            )

    machine = {
        "findings": [finding.as_dict() for finding in findings],
        "counts": counts,
        "total": len(findings),
    }
    return "\n".join(lines), machine


def persist_report(
    findings: Sequence[Finding],
    *,
    root: Optional[Path] = None,
    title: str = "Wiki Evaluation Report",
    updated: Optional[str] = None,
) -> Tuple[Path, Path]:
    """Write governed report artifacts to ``reviews/``.

    Produces two files under *root* (defaults to the repository root inferred
    from this module's location):

    ``reviews/health-report.md``
        A Markdown artifact with required frontmatter fields
        (``artifact_type: review``, ``status: active``, ``title``, ``updated``)
        so it passes ``tools/validate_repo.py``.

    ``reviews/health-report.json``
        A machine-readable JSON companion carrying the same findings as
        ``render_report`` returns.

    The report is **advisory**: this function never changes any exit status.

    Parameters
    ----------
    findings:
        The findings to persist, as returned by :func:`run_suite`.
    root:
        Repository root directory. Defaults to the parent of this package's
        parent (``tools/eval/`` → ``tools/`` → repo root).
    title:
        Human-readable title stored in the frontmatter ``title`` field.
    updated:
        ISO-8601 date string (``YYYY-MM-DD``) for the ``updated`` field.
        Defaults to today's date.

    Returns
    -------
    (md_path, json_path)
        Absolute :class:`~pathlib.Path` objects for the two written files.
    """

    if root is None:
        # tools/eval/__init__.py → tools/eval/ → tools/ → repo root
        root = Path(__file__).resolve().parents[2]
    if updated is None:
        updated = date.today().isoformat()

    markdown_body, machine = render_report(findings)

    # Build the governed Markdown artifact with required frontmatter.
    frontmatter_lines = [
        "---",
        "artifact_type: review",
        "status: active",
        f'title: "{title}"',
        f"updated: {updated}",
        "---",
        "",
    ]
    md_content = "\n".join(frontmatter_lines) + markdown_body

    reviews_dir = Path(root) / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)

    md_path = reviews_dir / "health-report.md"
    md_path.write_text(md_content, encoding="utf-8")

    json_path = reviews_dir / "health-report.json"
    json_path.write_text(json.dumps(machine, indent=2, ensure_ascii=False), encoding="utf-8")

    return md_path, json_path
