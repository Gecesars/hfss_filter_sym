from __future__ import annotations

import os
import platform
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

import psutil


@dataclass(frozen=True)
class AedtInstallation:
    version: str
    code: str
    root: Path
    executable: Path
    source: str

    def to_json(self) -> dict[str, str]:
        payload = asdict(self)
        payload["root"] = str(self.root)
        payload["executable"] = str(self.executable)
        return payload


def detect_aedt_installations(
    environment: Mapping[str, str] | None = None,
) -> list[AedtInstallation]:
    values = environment or os.environ
    candidates: list[AedtInstallation] = []

    for name, raw_path in values.items():
        if not name.startswith("ANSYSEM_ROOT"):
            continue
        code = name.removeprefix("ANSYSEM_ROOT")
        root = Path(raw_path)
        executable = _find_executable(root)
        if executable:
            candidates.append(
                AedtInstallation(
                    version=_version_from_code(code),
                    code=code,
                    root=executable.parent,
                    executable=executable,
                    source=f"environment:{name}",
                )
            )

    program_files = Path(values.get("ProgramFiles", r"C:\Program Files"))
    scan_patterns = [
        program_files / "ANSYS Inc",
        program_files / "AnsysEM",
    ]
    for base in scan_patterns:
        if not base.is_dir():
            continue
        for version_dir in base.glob("v[0-9][0-9][0-9]"):
            code = version_dir.name.removeprefix("v")
            for root in (version_dir / "AnsysEM", version_dir / "Win64", version_dir):
                executable = _find_executable(root)
                if executable:
                    candidates.append(
                        AedtInstallation(
                            version=_version_from_code(code),
                            code=code,
                            root=executable.parent,
                            executable=executable,
                            source="program-files",
                        )
                    )
                    break

    deduplicated: dict[str, AedtInstallation] = {}
    for installation in candidates:
        current = deduplicated.get(installation.version)
        if current is None or installation.source.startswith("environment"):
            deduplicated[installation.version] = installation
    return sorted(
        deduplicated.values(),
        key=lambda item: _version_tuple(item.version),
        reverse=True,
    )


def aedt_environment_diagnostics() -> dict[str, object]:
    installations = detect_aedt_installations()
    return {
        "platform": platform.platform(),
        "python": sys.version,
        "python_executable": sys.executable,
        "pyaedt_version": _distribution_version("pyaedt"),
        "installations": [installation.to_json() for installation in installations],
        "running_sessions": detect_running_aedt_sessions(),
        "recommended_version": installations[0].version if installations else None,
        "aedt_2026_available": any(
            installation.version.startswith("2026.") for installation in installations
        ),
    }


def detect_running_aedt_sessions() -> list[dict[str, object]]:
    sessions = []
    for process in psutil.process_iter(["pid", "name", "exe", "cmdline", "create_time"]):
        try:
            info = process.info
            if str(info.get("name") or "").lower() != "ansysedt.exe":
                continue
            command = [str(value) for value in info.get("cmdline") or []]
            port = _argument_value(command, "-grpcsrv")
            executable = str(info.get("exe") or "")
            sessions.append(
                {
                    "process_id": int(info["pid"]),
                    "grpc_port": int(port) if port and port.isdigit() else None,
                    "version": _version_from_executable(executable),
                    "executable": executable,
                    "non_graphical": "-ng" in command,
                    "created_at": float(info.get("create_time") or 0),
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, ValueError):
            continue
    return sorted(
        sessions,
        key=lambda item: float(item["created_at"]),
        reverse=True,
    )


def _find_executable(root: Path) -> Path | None:
    for candidate in (
        root / "ansysedt.exe",
        root / "Win64" / "ansysedt.exe",
        root / "AnsysEM" / "ansysedt.exe",
    ):
        if candidate.is_file():
            return candidate.resolve()
    return None


def _version_from_code(code: str) -> str:
    digits = "".join(character for character in code if character.isdigit())
    if len(digits) == 3:
        year = 2000 + int(digits[:2])
        release = int(digits[2])
        return f"{year}.{release}"
    return code


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return (0,)


def _distribution_version(name: str) -> str | None:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return None


def _argument_value(arguments: list[str], name: str) -> str | None:
    try:
        index = arguments.index(name)
    except ValueError:
        return None
    next_index = index + 1
    return arguments[next_index] if next_index < len(arguments) else None


def _version_from_executable(executable: str) -> str | None:
    normalized = executable.replace("/", "\\").lower()
    for part in normalized.split("\\"):
        if len(part) == 4 and part.startswith("v") and part[1:].isdigit():
            return _version_from_code(part[1:])
    return None
