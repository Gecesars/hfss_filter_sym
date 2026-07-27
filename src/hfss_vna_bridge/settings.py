from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    default_aedt_project: Path | None = None
    default_aedt_design: str | None = None
    default_aedt_version: str = "2026.1"
    default_vna_backend: str = "simulated"
    default_vna_resource: str = "SIM::VNA"

    @classmethod
    def from_env(cls) -> Settings:
        project = os.getenv("HFSS_BRIDGE_AEDT_PROJECT")
        return cls(
            host=os.getenv("HFSS_BRIDGE_HOST", "127.0.0.1"),
            port=int(os.getenv("HFSS_BRIDGE_PORT", "8765")),
            default_aedt_project=Path(project) if project else None,
            default_aedt_design=os.getenv("HFSS_BRIDGE_AEDT_DESIGN"),
            default_aedt_version=os.getenv("HFSS_BRIDGE_AEDT_VERSION", "2026.1"),
            default_vna_backend=os.getenv("HFSS_BRIDGE_VNA_BACKEND", "simulated"),
            default_vna_resource=os.getenv("HFSS_BRIDGE_VNA_RESOURCE", "SIM::VNA"),
        )
