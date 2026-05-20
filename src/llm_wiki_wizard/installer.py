"""Safe installer for namespaced LLM wiki workspaces."""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Iterator

from copier import run_copy

from . import __version__


SCAFFOLD_VERSION = "0.1.0"
WIKI_DIRNAME = ".llm-wiki"
INSTALL_MANIFEST = Path("meta/install.json")
INSTALL_REPORT = Path("meta/install-report.md")
COPIER_ANSWERS = ".copier-answers.yml"

POINTER_START = "<!-- llm-wiki:start -->"
POINTER_END = "<!-- llm-wiki:end -->"
POINTER_BLOCK = "\n".join(
    [
        POINTER_START,
        "## LLM Wiki",
        "",
        "This repository has a namespaced LLM wiki at `.llm-wiki/`.",
        "Agents should read `.llm-wiki/AGENTS.md` before creating or changing durable wiki artifacts.",
        POINTER_END,
        "",
    ]
)


class InstallerError(RuntimeError):
    """Raised when installation cannot proceed safely."""


@dataclass(frozen=True)
class InitResult:
    target: Path
    wiki_dir: Path
    dry_run: bool
    created_files: list[str]
    unchanged_files: list[str]
    conflicts: list[str]
    pointer_action: str
    install_manifest: str
    install_report: str

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target.as_posix(),
            "wiki_dir": self.wiki_dir.as_posix(),
            "dry_run": self.dry_run,
            "created_files": self.created_files,
            "unchanged_files": self.unchanged_files,
            "conflicts": self.conflicts,
            "pointer_action": self.pointer_action,
            "install_manifest": self.install_manifest,
            "install_report": self.install_report,
        }


@dataclass(frozen=True)
class StatusResult:
    target: Path
    wiki_exists: bool
    root_pointer_exists: bool
    scaffold_version: str
    installer_version: str
    missing_managed_files: list[str]
    changed_managed_files: list[str]
    unresolved_conflict_reports: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target.as_posix(),
            "wiki_exists": self.wiki_exists,
            "root_pointer_exists": self.root_pointer_exists,
            "scaffold_version": self.scaffold_version,
            "installer_version": self.installer_version,
            "missing_managed_files": self.missing_managed_files,
            "changed_managed_files": self.changed_managed_files,
            "unresolved_conflict_reports": self.unresolved_conflict_reports,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_target(target: Path | str) -> Path:
    path = Path(target).expanduser().resolve()
    if not path.exists():
        raise InstallerError(f"Target directory does not exist: {path}")
    if not path.is_dir():
        raise InstallerError(f"Target is not a directory: {path}")
    return path


def template_root() -> Path:
    return Path(str(resources.files("llm_wiki_wizard").joinpath("templates/wiki")))


@contextmanager
def rendered_template() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="llm-wiki-template-") as tmp:
        rendered = Path(tmp) / "rendered"
        run_copy(
            str(template_root()),
            rendered,
            data={},
            defaults=True,
            overwrite=True,
            quiet=True,
            skip_tasks=True,
        )
        yield rendered


def iter_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != COPIER_ANSWERS
    )


def relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def render_manifest(rendered: Path) -> dict[str, str]:
    return {
        relpath(path, rendered): sha256_file(path)
        for path in iter_files(rendered)
    }


def root_pointer_state(target: Path) -> str:
    agents = target / "AGENTS.md"
    if not agents.exists():
        return "missing"
    text = agents.read_text(encoding="utf-8")
    has_start = POINTER_START in text
    has_end = POINTER_END in text
    if has_start and has_end:
        return "present"
    if has_start or has_end:
        return "conflict"
    return "absent"


def apply_root_pointer(target: Path, *, dry_run: bool) -> str:
    agents = target / "AGENTS.md"
    state = root_pointer_state(target)
    if state == "present":
        return "present"
    if state == "conflict":
        return "conflict"
    if state == "missing":
        if not dry_run:
            agents.write_text(POINTER_BLOCK, encoding="utf-8")
        return "would_create" if dry_run else "created"
    if state == "absent":
        if not dry_run:
            text = agents.read_text(encoding="utf-8")
            separator = "\n\n" if text and not text.endswith("\n\n") else ""
            agents.write_text(text + separator + POINTER_BLOCK, encoding="utf-8")
        return "would_append" if dry_run else "appended"
    return state


def existing_created_at(manifest_path: Path) -> str | None:
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = data.get("created_at")
    return str(value) if value else None


def write_install_manifest(
    wiki_dir: Path,
    managed_files: dict[str, str],
    conflicts: list[str],
    pointer_action: str,
) -> None:
    manifest_path = wiki_dir / INSTALL_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = existing_created_at(manifest_path) or utc_now()
    data = {
        "template_version": SCAFFOLD_VERSION,
        "installer_version": __version__,
        "layout": WIKI_DIRNAME,
        "created_at": created_at,
        "updated_at": utc_now(),
        "managed_files": managed_files,
        "last_conflicts": conflicts,
        "root_pointer_action": pointer_action,
    }
    manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_install_report(wiki_dir: Path, result: InitResult) -> None:
    report_path = wiki_dir / INSTALL_REPORT
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "artifact_type: log",
        "status: active",
        "owner: installer",
        f"updated: {utc_now()}",
        "---",
        "",
        "# LLM Wiki Install Report",
        "",
        f"- Dry run: {str(result.dry_run).lower()}",
        f"- Files created: {len(result.created_files)}",
        f"- Files unchanged: {len(result.unchanged_files)}",
        f"- Conflicts: {len(result.conflicts)}",
        f"- Root AGENTS pointer: {result.pointer_action}",
        "",
        "## Conflicts",
        "",
    ]
    if result.conflicts:
        lines.extend(f"- `{path}`" for path in result.conflicts)
    else:
        lines.append("- None")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def initialize(target: Path | str, *, dry_run: bool = False) -> InitResult:
    target_path = resolve_target(target)
    wiki_dir = target_path / WIKI_DIRNAME
    created_files: list[str] = []
    unchanged_files: list[str] = []
    conflicts: list[str] = []

    with rendered_template() as rendered:
        managed_files = render_manifest(rendered)
        for source in iter_files(rendered):
            relative = relpath(source, rendered)
            destination = wiki_dir / relative
            source_bytes = source.read_bytes()
            if destination.exists():
                if sha256_file(destination) == sha256_bytes(source_bytes):
                    unchanged_files.append(relative)
                else:
                    conflicts.append(relative)
                continue
            created_files.append(relative)
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    pointer_action = apply_root_pointer(target_path, dry_run=dry_run)
    if pointer_action == "conflict":
        conflicts.append("AGENTS.md")

    result = InitResult(
        target=target_path,
        wiki_dir=wiki_dir,
        dry_run=dry_run,
        created_files=created_files,
        unchanged_files=unchanged_files,
        conflicts=sorted(conflicts),
        pointer_action=pointer_action,
        install_manifest=(wiki_dir / INSTALL_MANIFEST).as_posix(),
        install_report=(wiki_dir / INSTALL_REPORT).as_posix(),
    )
    if not dry_run:
        wiki_dir.mkdir(parents=True, exist_ok=True)
        write_install_manifest(wiki_dir, managed_files, result.conflicts, pointer_action)
        write_install_report(wiki_dir, result)
    return result


def read_install_manifest(wiki_dir: Path) -> dict[str, object]:
    manifest_path = wiki_dir / INSTALL_MANIFEST
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def status(target: Path | str) -> StatusResult:
    target_path = resolve_target(target)
    wiki_dir = target_path / WIKI_DIRNAME
    manifest = read_install_manifest(wiki_dir)
    managed_files = manifest.get("managed_files")
    if not isinstance(managed_files, dict):
        managed_files = {}

    missing: list[str] = []
    changed: list[str] = []
    for relative, expected in sorted(managed_files.items()):
        path = wiki_dir / str(relative)
        if not path.exists():
            missing.append(str(relative))
        elif sha256_file(path) != str(expected):
            changed.append(str(relative))

    conflicts = manifest.get("last_conflicts")
    unresolved_reports = []
    if isinstance(conflicts, list) and conflicts:
        unresolved_reports.append((wiki_dir / INSTALL_REPORT).as_posix())

    return StatusResult(
        target=target_path,
        wiki_exists=wiki_dir.exists(),
        root_pointer_exists=root_pointer_state(target_path) == "present",
        scaffold_version=str(manifest.get("template_version", "")),
        installer_version=str(manifest.get("installer_version", "")),
        missing_managed_files=missing,
        changed_managed_files=changed,
        unresolved_conflict_reports=unresolved_reports,
    )
