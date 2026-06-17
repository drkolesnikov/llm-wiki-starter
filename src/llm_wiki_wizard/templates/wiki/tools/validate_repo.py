#!/usr/bin/env python3
"""Structural checks for the LLM wiki starter repository."""

from __future__ import annotations

import re
import sys
import argparse
from collections import Counter
from pathlib import Path

try:  # script invocation: ``tools/`` is on sys.path[0]
    from wiki_spec import (
        ALLOWED_ARTIFACT_TYPES,
        ALLOWED_SOURCE_TIERS,
        ALLOWED_STATUSES,
        SKIP_DIRS,
    )
except ImportError:  # imported as ``tools.validate_repo``
    from tools.wiki_spec import (
        ALLOWED_ARTIFACT_TYPES,
        ALLOWED_SOURCE_TIERS,
        ALLOWED_STATUSES,
        SKIP_DIRS,
    )


ROOT = Path(__file__).resolve().parents[1]

# Portable-core fields per docs/llm-wiki-format.md §4. The portable-profile
# tier *fails* on the three load-bearing fields below and *reports* the
# remaining recommended core fields without failing (see issue #30).
PORTABLE_REQUIRED_FIELDS = ("artifact_type", "title", "updated")
PORTABLE_RECOMMENDED_FIELDS = ("description", "resource")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
CODE_SPAN_RE = re.compile(r"(`+).*?\1", re.DOTALL)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in path.parts)
    )


def split_frontmatter(text: str) -> tuple[dict[str, object], int] | tuple[None, int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0
    for end_index in range(1, len(lines)):
        if lines[end_index].strip() == "---":
            return parse_frontmatter(lines[1:end_index]), end_index + 1
    return {}, len(lines)


def parse_frontmatter(lines: list[str]) -> dict[str, object]:
    data: dict[str, object] = {}
    current_key: str | None = None
    for raw_line in lines:
        if not raw_line.strip():
            continue
        if raw_line.startswith("  - ") and current_key:
            value = raw_line[4:].strip()
            current = data.setdefault(current_key, [])
            if isinstance(current, list):
                current.append(clean_scalar(value))
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "[]":
            data[key] = []
        elif value:
            data[key] = clean_scalar(value)
        else:
            data[key] = []
    return data


def clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def should_require_frontmatter(path: Path) -> bool:
    if path.name == "README.md":
        return False
    if ".github" in path.parts:
        return False
    if "templates" in path.parts:
        return False
    rel_path = rel(path)
    return (
        rel_path.startswith("meta/")
        or rel_path.startswith("knowledge/")
        or rel_path.startswith("reviews/")
        or rel_path.startswith("projects/")
        or rel_path.startswith("raw/derived/")
        or rel_path == "docs/source-ingest-policy.md"
    )


def registered_sources(root: Path | None = None) -> dict[str, dict[str, str]]:
    registry_path = (root if root is not None else ROOT) / "meta" / "source-registry.md"
    if not registry_path.exists():
        return {}
    sources: dict[str, dict[str, str]] = {}
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"Source ID", "---"} or set(cells[0]) == {"-"}:
            continue
        if len(cells) < 6:
            continue
        source_id, title, tier, status, derived_path, notes = cells[:6]
        if source_id and source_id != "-":
            sources[source_id] = {
                "title": title,
                "tier": tier,
                "status": status,
                "derived_path": derived_path,
                "notes": notes,
            }
    return sources


def source_values(frontmatter: dict[str, object]) -> list[str]:
    raw = frontmatter.get("sources")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    value = str(raw).strip()
    return [value] if value else []


def validate_frontmatter(errors: list[str], sources: dict[str, dict[str, str]]) -> None:
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        frontmatter, _ = split_frontmatter(text)
        if frontmatter is None:
            if should_require_frontmatter(path):
                errors.append(f"{rel(path)}: missing frontmatter")
            continue
        artifact_type = frontmatter.get("artifact_type")
        status = frontmatter.get("status")
        if artifact_type is not None and artifact_type not in ALLOWED_ARTIFACT_TYPES:
            errors.append(f"{rel(path)}: unknown artifact_type {artifact_type!r}")
        if status is not None and status not in ALLOWED_STATUSES:
            errors.append(f"{rel(path)}: unknown status {status!r}")
        source_tier = frontmatter.get("source_tier")
        if source_tier is not None and source_tier not in ALLOWED_SOURCE_TIERS:
            errors.append(f"{rel(path)}: unknown source_tier {source_tier!r}")
        if should_require_frontmatter(path):
            if artifact_type is None:
                errors.append(f"{rel(path)}: missing artifact_type")
            if status is None:
                errors.append(f"{rel(path)}: missing status")
        for source_id in source_values(frontmatter):
            if source_id not in sources:
                errors.append(f"{rel(path)}: source {source_id!r} is not registered")


def validate_registry(errors: list[str], sources: dict[str, dict[str, str]]) -> None:
    for source_id, row in sources.items():
        tier = row["tier"]
        status = row["status"]
        derived_path = row["derived_path"]
        if tier not in ALLOWED_SOURCE_TIERS:
            errors.append(f"meta/source-registry.md: source {source_id!r} has unknown tier {tier!r}")
        if status not in ALLOWED_STATUSES:
            errors.append(f"meta/source-registry.md: source {source_id!r} has unknown status {status!r}")
        if derived_path and derived_path != "-":
            target = (ROOT / derived_path).resolve()
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"meta/source-registry.md: source {source_id!r} derived path leaves repository")
                continue
            if not target.exists():
                errors.append(f"meta/source-registry.md: source {source_id!r} derived path is missing: {derived_path}")


def validate_links(errors: list[str]) -> None:
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            href = match.group(1).strip()
            if should_skip_link(href):
                continue
            target_text = href.split("#", 1)[0]
            if not target_text:
                continue
            target = (path.parent / target_text).resolve()
            try:
                target.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{rel(path)}: link leaves repository: {href}")
                continue
            if not target.exists():
                errors.append(f"{rel(path)}: broken link: {href}")


def linked_markdown_targets() -> set[str]:
    targets: set[str] = set()
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            href = match.group(1).strip()
            if should_skip_link(href):
                continue
            target_text = href.split("#", 1)[0]
            if not target_text:
                continue
            target = (path.parent / target_text).resolve()
            try:
                targets.add(rel(target))
            except ValueError:
                continue
    return targets


def title_values(path: Path, frontmatter: dict[str, object]) -> set[str]:
    values = {path.stem}
    title = frontmatter.get("title")
    if title:
        values.add(str(title).strip())
    aliases = frontmatter.get("aliases")
    if isinstance(aliases, list):
        values.update(str(alias).strip() for alias in aliases if str(alias).strip())
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            values.add(line[2:].strip())
            break
    return {value.casefold() for value in values if value}


def health_report(sources: dict[str, dict[str, str]]) -> str:
    frontmatter_by_path: dict[Path, dict[str, object]] = {}
    for path in markdown_files():
        frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        if frontmatter:
            frontmatter_by_path[path] = frontmatter

    status_counts = Counter(
        str(frontmatter.get("status"))
        for frontmatter in frontmatter_by_path.values()
        if frontmatter.get("status")
    )
    unresolved = [
        f"{rel(path)} ({frontmatter.get('status')})"
        for path, frontmatter in frontmatter_by_path.items()
        if frontmatter.get("status") in {"needs-review", "conflicted"}
    ]

    linked_targets = linked_markdown_targets()
    orphan_candidates = [
        rel(path)
        for path, frontmatter in frontmatter_by_path.items()
        if is_health_artifact(path, frontmatter) and rel(path) not in linked_targets
    ]

    known_titles: set[str] = set()
    for path, frontmatter in frontmatter_by_path.items():
        known_titles.update(title_values(path, frontmatter))

    unresolved_wikilinks: set[str] = set()
    for path in markdown_files():
        text = strip_inline_code(path.read_text(encoding="utf-8"))
        for target in WIKILINK_RE.findall(text):
            if target.strip().casefold() not in known_titles:
                unresolved_wikilinks.add(f"{rel(path)} -> [[{target.strip()}]]")

    lines = [
        "",
        "Wiki health report",
        "==================",
        "Status counts:",
    ]
    if status_counts:
        lines.extend(f"- {status}: {count}" for status, count in sorted(status_counts.items()))
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Unresolved statuses:")
    lines.extend(format_report_items(unresolved))

    lines.append("")
    lines.append("Orphan candidates:")
    lines.extend(format_report_items(orphan_candidates))

    lines.append("")
    lines.append("Unresolved wikilinks:")
    lines.extend(format_report_items(sorted(unresolved_wikilinks)))

    lines.append("")
    lines.append("Registered sources:")
    lines.append(f"- {len(sources)}")
    return "\n".join(lines)


def eval_findings_report(model=None) -> str:
    """Render the advisory eval suite (issue #35) as a report block.

    Runs the auto-discovered signal suite from :mod:`tools.eval` against the
    parsed :class:`RepoModel` and renders its findings. Eval findings are
    **advisory**: this returns text only and never affects exit status.
    """

    try:  # script invocation: ``tools/`` is on sys.path[0]
        from eval import render_report, run_suite
    except ImportError:  # imported as ``tools.validate_repo``
        from tools.eval import render_report, run_suite
    if model is None:
        model = _load_repo_model()
    markdown, _machine = render_report(run_suite(model))
    return "\n" + markdown


def is_health_artifact(path: Path, frontmatter: dict[str, object]) -> bool:
    artifact_type = frontmatter.get("artifact_type")
    if artifact_type in {"index", "log", "source-registry"}:
        return False
    rel_path = rel(path)
    return rel_path.startswith(("knowledge/", "reviews/", "projects/"))


def format_report_items(items: list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item}" for item in items]


def strip_inline_code(text: str) -> str:
    return CODE_SPAN_RE.sub("", text)


def should_skip_link(href: str) -> bool:
    lowered = href.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("#")
        or lowered.startswith("tel:")
    )


def _load_repo_model():
    """Load the parsed :class:`RepoModel` rooted at the current ``ROOT``.

    Imported lazily and rooted at the module-level ``ROOT`` so tests that
    monkeypatch ``validate_repo.ROOT`` see the override.
    """

    try:  # script invocation: ``tools/`` is on sys.path[0]
        from wiki_model import load_repo_model
    except ImportError:  # imported as ``tools.validate_repo``
        from tools.wiki_model import load_repo_model
    return load_repo_model(ROOT)


def _run_structural_checks(errors: list[str], model=None) -> None:
    """Run every auto-discovered structural check in sorted filename order.

    The check registry lives in the ``checks`` package next to this module so
    new checks are add-a-file. ``model`` is parsed lazily when not supplied so
    callers that already have one avoid re-parsing.
    """

    try:  # script invocation: ``tools/`` is on sys.path[0]
        import checks
    except ImportError:  # imported as ``tools.validate_repo``
        from tools import checks
    if model is None:
        model = _load_repo_model()
    checks.run_checks(model, errors)


def valid_iso_date(value: object) -> bool:
    """Return ``True`` when ``value`` is a ``YYYY-MM-DD`` calendar date."""

    return isinstance(value, str) and bool(ISO_DATE_RE.match(value.strip()))


def portable_profile_report(model=None) -> tuple[str, int]:
    """Evaluate the portable-profile tier; return ``(report_text, failures)``.

    Per issue #30, an artifact *fails* the portable profile when it is missing
    ``artifact_type``, ``title``, or a valid ISO-8601 (``YYYY-MM-DD``)
    ``updated`` field. Missing recommended core fields (``description``,
    ``resource``) are *reported* but do not count as failures. Only artifacts
    that carry frontmatter and are durable (``should_require_frontmatter``) are
    evaluated, mirroring the structural tier's scope.
    """

    if model is None:
        model = _load_repo_model()

    failures: list[str] = []
    advisories: list[str] = []
    for artifact in model.artifacts:
        if not should_require_frontmatter(artifact.path):
            continue
        frontmatter = artifact.frontmatter
        if not frontmatter:
            failures.append(f"{rel(artifact.path)}: missing frontmatter")
            continue
        for field_name in PORTABLE_REQUIRED_FIELDS:
            value = frontmatter.get(field_name)
            if field_name == "updated":
                if not valid_iso_date(value):
                    if value in (None, "", []):
                        failures.append(f"{rel(artifact.path)}: missing portable-core field 'updated'")
                    else:
                        failures.append(
                            f"{rel(artifact.path)}: 'updated' is not an ISO-8601 (YYYY-MM-DD) date: {value!r}"
                        )
                continue
            if value in (None, "", []):
                failures.append(f"{rel(artifact.path)}: missing portable-core field {field_name!r}")
        for field_name in PORTABLE_RECOMMENDED_FIELDS:
            value = frontmatter.get(field_name)
            if value in (None, "", []):
                advisories.append(f"{rel(artifact.path)}: missing recommended core field {field_name!r}")

    lines = [
        "",
        "Portable-profile report",
        "=======================",
        "Failures (missing artifact_type/title or invalid updated):",
    ]
    lines.extend(format_report_items(failures))
    lines.append("")
    lines.append("Advisories (missing recommended core fields):")
    lines.extend(format_report_items(advisories))
    return "\n".join(lines), len(failures)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate structural wiki repository rules.")
    parser.add_argument(
        "--tier",
        action="append",
        choices=["structural", "portable", "health"],
        dest="tiers",
        help=(
            "Conformance tier to run (repeatable). 'structural' (default) is "
            "blocking; 'portable' enforces the portable-core profile; 'health' "
            "prints non-blocking health signals. Omit to run structural only."
        ),
    )
    parser.add_argument(
        "--health-report",
        action="store_true",
        help="Print non-blocking wiki health signals after structural validation.",
    )
    return parser


def _run_structural_tier() -> int:
    """Run the structural tier; preserves today's output and exit codes."""

    errors: list[str] = []
    _run_structural_checks(errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"\nRepository validation failed with {len(errors)} issue(s).")
        return 1
    print("Repository validation passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # No --tier selection preserves today's behavior byte-for-byte: run the
    # structural tier, then optionally append the health report (exit 0).
    if not args.tiers:
        sources = registered_sources()
        errors: list[str] = []
        _run_structural_checks(errors, _load_repo_model())
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            print(f"\nRepository validation failed with {len(errors)} issue(s).")
            return 1
        print("Repository validation passed.")
        if args.health_report:
            print(health_report(sources))
        return 0

    # Explicit tier selection: run each requested tier once, labeled, in a
    # stable order. Only the structural tier is blocking.
    exit_code = 0
    tier_order = [t for t in ("structural", "portable", "health") if t in set(args.tiers)]
    for tier in tier_order:
        if tier == "structural":
            print("[tier: structural]")
            if _run_structural_tier() != 0:
                exit_code = 1
        elif tier == "portable":
            print("[tier: portable-profile]")
            report, failures = portable_profile_report()
            print(report)
            if failures:
                print(f"\nPortable-profile failed with {failures} issue(s).")
                exit_code = 1
            else:
                print("\nPortable-profile passed.")
        elif tier == "health":
            print("[tier: advisory-health]")
            print(health_report(registered_sources()))
            print(eval_findings_report())

    if args.health_report and "health" not in tier_order:
        print(health_report(registered_sources()))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
