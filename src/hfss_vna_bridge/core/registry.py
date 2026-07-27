from __future__ import annotations

from dataclasses import dataclass, field

from hfss_vna_bridge.adapters.aedt.base import AedtAdapter
from hfss_vna_bridge.adapters.aedt.simulated import SimulatedAedtAdapter
from hfss_vna_bridge.adapters.vna.base import VnaAdapter
from hfss_vna_bridge.adapters.vna.simulated import SimulatedVnaAdapter
from hfss_vna_bridge.settings import Settings


@dataclass
class RuntimeRegistry:
    settings: Settings
    aedt: AedtAdapter = field(default_factory=SimulatedAedtAdapter)
    vna: VnaAdapter = field(default_factory=SimulatedVnaAdapter)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> RuntimeRegistry:
        return cls(settings=settings or Settings.from_env())
