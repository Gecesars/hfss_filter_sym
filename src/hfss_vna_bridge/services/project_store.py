from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

PROJECT_FORMAT = "hfss-filter-studio-project"
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class ProjectStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def list_projects(self) -> list[dict[str, Any]]:
        projects = []
        with self._lock:
            for directory in self.root.iterdir():
                if not directory.is_dir():
                    continue
                current = directory / "project.json"
                if not current.is_file():
                    continue
                try:
                    project = _read_json(current)
                except (OSError, ValueError):
                    continue
                projects.append(_summary(project))
        return sorted(projects, key=lambda item: str(item["updated_at"]), reverse=True)

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = _normalize_project(payload)
        project_id = str(payload.get("id") or _project_id(project["name"]))
        directory = self._directory(project_id)
        with self._lock:
            if directory.exists():
                project_id = f"{project_id}-{uuid4().hex[:6]}"
                directory = self._directory(project_id)
            directory.mkdir(parents=True)
            now = _timestamp()
            project.update({"id": project_id, "created_at": now, "updated_at": now, "revision": 1})
            _write_json(directory / "project.json", project)
            self._write_version(directory, project)
        return deepcopy(project)

    def get(self, project_id: str) -> dict[str, Any]:
        with self._lock:
            return _read_json(self._directory(project_id) / "project.json")

    def update(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        directory = self._directory(project_id)
        with self._lock:
            current = _read_json(directory / "project.json")
            candidate = _normalize_project({**current, **payload})
            candidate.update(
                {
                    "id": project_id,
                    "created_at": current["created_at"],
                    "updated_at": _timestamp(),
                    "revision": int(current.get("revision", 0)) + 1,
                }
            )
            _write_json(directory / "project.json", candidate)
            self._write_version(directory, candidate)
        return deepcopy(candidate)

    def delete(self, project_id: str) -> bool:
        directory = self._directory(project_id)
        with self._lock:
            if not directory.exists():
                return False
            for path in sorted(directory.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            directory.rmdir()
        return True

    def versions(self, project_id: str) -> list[dict[str, Any]]:
        directory = self._directory(project_id) / "versions"
        if not directory.is_dir():
            return []
        versions = []
        with self._lock:
            for path in sorted(directory.glob("*.json"), reverse=True):
                project = _read_json(path)
                versions.append(_summary(project))
        return versions

    def restore(self, project_id: str, revision: int) -> dict[str, Any]:
        directory = self._directory(project_id)
        version_path = directory / "versions" / f"{revision:06d}.json"
        with self._lock:
            restored = _read_json(version_path)
            current = _read_json(directory / "project.json")
            restored.update(
                {
                    "id": project_id,
                    "created_at": current["created_at"],
                    "updated_at": _timestamp(),
                    "revision": int(current.get("revision", 0)) + 1,
                }
            )
            _write_json(directory / "project.json", restored)
            self._write_version(directory, restored)
        return deepcopy(restored)

    def _directory(self, project_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", project_id):
            raise ValueError("Invalid project id")
        directory = (self.root / project_id).resolve()
        if self.root not in directory.parents:
            raise ValueError("Project path escapes the project store")
        return directory

    @staticmethod
    def _write_version(directory: Path, project: dict[str, Any]) -> None:
        versions = directory / "versions"
        versions.mkdir(exist_ok=True)
        revision = int(project["revision"])
        _write_json(versions / f"{revision:06d}.json", project)


def _normalize_project(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "Filter Project").strip()
    if not name:
        raise ValueError("Project name is required")
    specification = payload.get("specification", {})
    if not isinstance(specification, dict):
        raise TypeError("Project specification must be an object")
    matrix = payload.get("matrix")
    if matrix is not None and not isinstance(matrix, dict):
        raise TypeError("Project matrix must be an object or null")
    return {
        "format": PROJECT_FORMAT,
        "version": 2,
        "name": name[:120],
        "description": str(payload.get("description") or "")[:2000],
        "specification": deepcopy(specification),
        "matrix": deepcopy(matrix),
        "integration": deepcopy(payload.get("integration") or {}),
        "measurements": deepcopy(payload.get("measurements") or {}),
        "metadata": deepcopy(payload.get("metadata") or {}),
    }


def _summary(project: dict[str, Any]) -> dict[str, Any]:
    specification = project.get("specification") or {}
    return {
        "id": project.get("id"),
        "name": project.get("name"),
        "description": project.get("description", ""),
        "revision": project.get("revision", 0),
        "updated_at": project.get("updated_at"),
        "created_at": project.get("created_at"),
        "filter_type": specification.get("filter_type"),
        "order": specification.get("order"),
        "f0_ghz": specification.get("f0_ghz"),
    }


def _project_id(name: str) -> str:
    slug = _SLUG_PATTERN.sub("-", name.lower()).strip("-")[:64]
    return slug or f"project-{uuid4().hex[:8]}"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Project not found: {path.parent.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Invalid project data: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
