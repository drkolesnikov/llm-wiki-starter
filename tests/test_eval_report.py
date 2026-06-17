"""Tests for eval report persistence (issue #49, G8).

Running this suite writes ``reviews/health-report.md`` and
``reviews/health-report.json`` into a temporary directory and verifies:

- The Markdown artifact's frontmatter passes the structural validator's
  required-fields logic (artifact_type, status, title, updated).
- The JSON companion is parseable and lists the same findings.
- The report is advisory: persist_report never raises, and its existence does
  not affect exit status.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from tools.eval import Finding, persist_report, render_report


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Frontmatter fields that must be present per validate_repo.py.
REQUIRED_FM_FIELDS = ("artifact_type", "status", "title", "updated")


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract the YAML frontmatter key-value pairs from *text*.

    Only handles flat scalar values (no lists, no nesting) — sufficient for
    the fields we need to assert.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        data[key] = value
    return data


class PersistReportFrontmatterTests(unittest.TestCase):
    """Verify that the generated Markdown artifact passes frontmatter checks."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _run(self, findings=(), **kwargs):
        return persist_report(list(findings), root=self.root, **kwargs)

    def test_required_frontmatter_fields_present_no_findings(self):
        md_path, _json_path = self._run()
        text = md_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        for field_name in REQUIRED_FM_FIELDS:
            self.assertIn(field_name, fm, f"Missing frontmatter field: {field_name!r}")

    def test_artifact_type_is_review(self):
        md_path, _ = self._run()
        fm = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
        self.assertEqual("review", fm.get("artifact_type"))

    def test_status_is_active(self):
        md_path, _ = self._run()
        fm = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
        self.assertEqual("active", fm.get("status"))

    def test_updated_is_iso_date(self):
        md_path, _ = self._run()
        fm = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
        updated = fm.get("updated", "")
        self.assertRegex(updated, ISO_DATE_RE, f"'updated' is not YYYY-MM-DD: {updated!r}")

    def test_explicit_updated_preserved(self):
        md_path, _ = self._run(updated="2024-01-15")
        fm = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
        self.assertEqual("2024-01-15", fm.get("updated"))

    def test_custom_title_in_frontmatter(self):
        md_path, _ = self._run(title="My Custom Report")
        fm = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
        self.assertEqual("My Custom Report", fm.get("title"))

    def test_default_title_present(self):
        md_path, _ = self._run()
        fm = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
        title = fm.get("title", "")
        self.assertTrue(title, "title frontmatter field must not be empty")

    def test_markdown_body_follows_frontmatter(self):
        md_path, _ = self._run()
        text = md_path.read_text(encoding="utf-8")
        # Frontmatter closes with '---'; body should come after.
        parts = text.split("---", 2)
        # parts[0] = '' (before opening ---), parts[1] = frontmatter, parts[2] = body
        self.assertGreaterEqual(len(parts), 3, "Expected two '---' fences")
        body = parts[2]
        self.assertIn("# Evaluation report", body)


class PersistReportJsonTests(unittest.TestCase):
    """Verify that the JSON companion is correct and parseable."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_json_parseable_no_findings(self):
        _, json_path = persist_report([], root=self.root)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertIn("findings", data)
        self.assertIn("counts", data)
        self.assertIn("total", data)

    def test_json_findings_match_input(self):
        findings = [
            Finding("sig-a", "deterministic", "info", ["x.md"], "explanation A"),
            Finding("sig-b", "llm", "warn", [], "explanation B"),
        ]
        _, json_path = persist_report(findings, root=self.root)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(2, data["total"])
        ids = {f["signal_id"] for f in data["findings"]}
        self.assertEqual({"sig-a", "sig-b"}, ids)

    def test_json_counts_match_findings(self):
        findings = [
            Finding("d1", "deterministic", "info", [], "d"),
            Finding("d2", "deterministic", "warn", [], "d"),
            Finding("l1", "llm", "info", [], "l"),
        ]
        _, json_path = persist_report(findings, root=self.root)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(2, data["counts"]["deterministic"])
        self.assertEqual(1, data["counts"]["llm"])

    def test_json_findings_have_all_keys(self):
        findings = [Finding("s", "deterministic", "info", ["a.md"], "why")]
        _, json_path = persist_report(findings, root=self.root)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        finding_dict = data["findings"][0]
        for key in ("signal_id", "finding_class", "severity", "implicated", "explanation"):
            self.assertIn(key, finding_dict)

    def test_json_and_markdown_agree_on_total(self):
        findings = [
            Finding("x", "deterministic", "info", [], "x"),
        ]
        md_path, json_path = persist_report(findings, root=self.root)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(1, data["total"])
        md_text = md_path.read_text(encoding="utf-8")
        self.assertIn("1 finding(s).", md_text)


class PersistReportFilesTests(unittest.TestCase):
    """Verify file paths and idempotency."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_returns_paths_to_written_files(self):
        md_path, json_path = persist_report([], root=self.root)
        self.assertTrue(md_path.exists(), "health-report.md must exist")
        self.assertTrue(json_path.exists(), "health-report.json must exist")

    def test_md_path_is_in_reviews_dir(self):
        md_path, _ = persist_report([], root=self.root)
        self.assertEqual("reviews", md_path.parent.name)

    def test_json_path_is_in_reviews_dir(self):
        _, json_path = persist_report([], root=self.root)
        self.assertEqual("reviews", json_path.parent.name)

    def test_idempotent_overwrite(self):
        """Calling persist_report twice overwrites without raising."""
        persist_report([], root=self.root)
        md_path, json_path = persist_report(
            [Finding("s", "deterministic", "info", [], "second run")],
            root=self.root,
        )
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(1, data["total"])

    def test_reviews_dir_created_if_missing(self):
        new_root = self.root / "subdir"
        new_root.mkdir()
        md_path, _ = persist_report([], root=new_root)
        self.assertTrue(md_path.exists())


class PersistReportValidatorCompatibilityTests(unittest.TestCase):
    """Run the repo validator's own frontmatter parser over the output."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_frontmatter_passes_validator_required_fields(self):
        """The validator requires artifact_type and status; portable tier
        also requires title and an ISO updated. Check all four."""
        from tools.validate_repo import (
            parse_frontmatter,
            split_frontmatter,
            valid_iso_date,
        )
        from tools.wiki_spec import ALLOWED_ARTIFACT_TYPES, ALLOWED_STATUSES

        md_path, _ = persist_report(
            [Finding("t", "deterministic", "info", [], "test")],
            root=self.root,
            updated="2025-03-01",
        )
        text = md_path.read_text(encoding="utf-8")
        fm, _ = split_frontmatter(text)
        self.assertIsNotNone(fm, "Frontmatter must be parseable")
        self.assertIn(fm.get("artifact_type"), ALLOWED_ARTIFACT_TYPES)
        self.assertIn(fm.get("status"), ALLOWED_STATUSES)
        self.assertTrue(fm.get("title"), "title must be non-empty")
        self.assertTrue(valid_iso_date(fm.get("updated")), "updated must be ISO date")
