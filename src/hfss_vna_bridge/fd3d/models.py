from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

FD3D_PROJECT_SCHEMA = "hfss-filter-studio/fd3d-project/v1"


class ProjectStage(StrEnum):
    SPECIFICATION = "SPECIFICATION"
    SYNTHESIS = "SYNTHESIS"
    TOPOLOGY = "TOPOLOGY"
    COMPONENT_LIBRARY = "COMPONENT_LIBRARY"
    CHARACTERIZATION = "CHARACTERIZATION"
    ASSEMBLY = "ASSEMBLY"
    FULLWAVE_ANALYSIS = "FULLWAVE_ANALYSIS"
    MATRIX_EXTRACTION = "MATRIX_EXTRACTION"
    OPTIMIZATION = "OPTIMIZATION"
    VNA_TUNING = "VNA_TUNING"
    RELEASED = "RELEASED"


class ComponentKind(StrEnum):
    RESONATOR = "RESONATOR"
    INTERNAL_COUPLING = "INTERNAL_COUPLING"
    EXTERNAL_COUPLING = "EXTERNAL_COUPLING"
    TERMINATION = "TERMINATION"
    HOUSING = "HOUSING"
    TUNING_FEATURE = "TUNING_FEATURE"
    NON_RESONATING_NODE = "NON_RESONATING_NODE"


class StudyKind(StrEnum):
    RESONANCE = "RESONANCE"
    COUPLING = "COUPLING"
    EXTERNAL_Q = "EXTERNAL_Q"
    SPURIOUS_MODES = "SPURIOUS_MODES"
    LOSS_Q = "LOSS_Q"


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    unit: str
    nominal: float
    minimum: float
    maximum: float
    samples: int = 7
    role: str = "tuning"
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("parameter name is required")
        if self.maximum <= self.minimum:
            raise ValueError(f"parameter {self.name!r} maximum must exceed minimum")
        if not self.minimum <= self.nominal <= self.maximum:
            raise ValueError(f"parameter {self.name!r} nominal must be within its bounds")
        if self.samples < 2:
            raise ValueError(f"parameter {self.name!r} requires at least two samples")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ParameterDefinition:
        return cls(
            name=str(value["name"]),
            unit=str(value.get("unit") or ""),
            nominal=float(value["nominal"]),
            minimum=float(value["minimum"]),
            maximum=float(value["maximum"]),
            samples=int(value.get("samples", 7)),
            role=str(value.get("role") or "tuning"),
            description=str(value.get("description") or ""),
        )


@dataclass(frozen=True)
class CharacterizationSample:
    parameter_value: float
    frequencies_hz: tuple[float, ...]
    quality_factors: tuple[float | None, ...] = ()
    mode_labels: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.frequencies_hz:
            raise ValueError("characterization sample requires at least one eigenfrequency")
        if any(value <= 0.0 for value in self.frequencies_hz):
            raise ValueError("eigenfrequencies must be greater than zero")
        if self.quality_factors and len(self.quality_factors) != len(self.frequencies_hz):
            raise ValueError("quality_factors must match frequencies_hz")
        if self.mode_labels and len(self.mode_labels) != len(self.frequencies_hz):
            raise ValueError("mode_labels must match frequencies_hz")

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_value": self.parameter_value,
            "frequencies_hz": list(self.frequencies_hz),
            "quality_factors": list(self.quality_factors),
            "mode_labels": list(self.mode_labels),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CharacterizationSample:
        return cls(
            parameter_value=float(value["parameter_value"]),
            frequencies_hz=tuple(float(item) for item in value["frequencies_hz"]),
            quality_factors=tuple(
                None if item is None else float(item)
                for item in value.get("quality_factors", [])
            ),
            mode_labels=tuple(str(item) for item in value.get("mode_labels", [])),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(frozen=True)
class CharacterizationCurve:
    curve_id: str
    study_kind: StudyKind
    parameter_name: str
    parameter_unit: str
    x_values: tuple[float, ...]
    response_name: str
    response_unit: str
    y_values: tuple[float, ...]
    monotonic_direction: str
    source_samples: tuple[CharacterizationSample, ...]
    approved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.curve_id.strip():
            raise ValueError("curve_id is required")
        if len(self.x_values) != len(self.y_values):
            raise ValueError("x_values and y_values must have the same length")
        if len(self.x_values) < 2:
            raise ValueError("a characterization curve requires at least two points")
        if any(b <= a for a, b in zip(self.x_values, self.x_values[1:], strict=False)):
            raise ValueError("x_values must be strictly increasing")
        if self.monotonic_direction not in {"increasing", "decreasing", "non_monotonic"}:
            raise ValueError("invalid monotonic_direction")

    def to_dict(self) -> dict[str, Any]:
        return {
            "curve_id": self.curve_id,
            "study_kind": self.study_kind.value,
            "parameter_name": self.parameter_name,
            "parameter_unit": self.parameter_unit,
            "x_values": list(self.x_values),
            "response_name": self.response_name,
            "response_unit": self.response_unit,
            "y_values": list(self.y_values),
            "monotonic_direction": self.monotonic_direction,
            "source_samples": [sample.to_dict() for sample in self.source_samples],
            "approved": self.approved,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CharacterizationCurve:
        return cls(
            curve_id=str(value["curve_id"]),
            study_kind=StudyKind(str(value["study_kind"])),
            parameter_name=str(value["parameter_name"]),
            parameter_unit=str(value.get("parameter_unit") or ""),
            x_values=tuple(float(item) for item in value["x_values"]),
            response_name=str(value["response_name"]),
            response_unit=str(value.get("response_unit") or ""),
            y_values=tuple(float(item) for item in value["y_values"]),
            monotonic_direction=str(value["monotonic_direction"]),
            source_samples=tuple(
                CharacterizationSample.from_dict(item)
                for item in value.get("source_samples", [])
            ),
            approved=bool(value.get("approved", False)),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ComponentDefinition:
    component_id: str
    name: str
    version: int
    technology: str
    kind: ComponentKind
    recipe: str
    parameters: tuple[ParameterDefinition, ...]
    interfaces: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.component_id.strip():
            raise ValueError("component_id is required")
        if self.version < 1:
            raise ValueError("component version must be at least one")
        names = [item.name for item in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError(f"component {self.component_id!r} has duplicate parameter names")

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "version": self.version,
            "technology": self.technology,
            "kind": self.kind.value,
            "recipe": self.recipe,
            "parameters": [item.to_dict() for item in self.parameters],
            "interfaces": [dict(item) for item in self.interfaces],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ComponentDefinition:
        return cls(
            component_id=str(value["component_id"]),
            name=str(value["name"]),
            version=int(value.get("version", 1)),
            technology=str(value["technology"]),
            kind=ComponentKind(str(value["kind"])),
            recipe=str(value["recipe"]),
            parameters=tuple(
                ParameterDefinition.from_dict(item)
                for item in value.get("parameters", [])
            ),
            interfaces=tuple(dict(item) for item in value.get("interfaces", [])),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(frozen=True)
class Fd3dProject:
    project_id: str
    name: str
    stage: ProjectStage
    specification: dict[str, Any]
    synthesis: dict[str, Any]
    components: tuple[ComponentDefinition, ...]
    assembly: dict[str, Any]
    characterizations: tuple[CharacterizationCurve, ...] = ()
    analyses: tuple[dict[str, Any], ...] = ()
    optimizations: tuple[dict[str, Any], ...] = ()
    tuning_sessions: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FD3D_PROJECT_SCHEMA,
            "project_id": self.project_id,
            "name": self.name,
            "stage": self.stage.value,
            "specification": dict(self.specification),
            "synthesis": dict(self.synthesis),
            "components": [item.to_dict() for item in self.components],
            "assembly": dict(self.assembly),
            "characterizations": [item.to_dict() for item in self.characterizations],
            "analyses": [dict(item) for item in self.analyses],
            "optimizations": [dict(item) for item in self.optimizations],
            "tuning_sessions": [dict(item) for item in self.tuning_sessions],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Fd3dProject:
        schema = str(value.get("schema") or FD3D_PROJECT_SCHEMA)
        if schema != FD3D_PROJECT_SCHEMA:
            raise ValueError(f"unsupported FD3D project schema: {schema}")
        return cls(
            project_id=str(value["project_id"]),
            name=str(value["name"]),
            stage=ProjectStage(str(value.get("stage") or ProjectStage.SPECIFICATION.value)),
            specification=dict(value.get("specification") or {}),
            synthesis=dict(value.get("synthesis") or {}),
            components=tuple(
                ComponentDefinition.from_dict(item)
                for item in value.get("components", [])
            ),
            assembly=dict(value.get("assembly") or {}),
            characterizations=tuple(
                CharacterizationCurve.from_dict(item)
                for item in value.get("characterizations", [])
            ),
            analyses=tuple(dict(item) for item in value.get("analyses", [])),
            optimizations=tuple(dict(item) for item in value.get("optimizations", [])),
            tuning_sessions=tuple(dict(item) for item in value.get("tuning_sessions", [])),
            metadata=dict(value.get("metadata") or {}),
        )
