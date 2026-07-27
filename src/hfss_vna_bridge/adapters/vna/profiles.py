from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScpiProfile:
    key: str
    display_name: str
    define_measurement: str
    select_measurement: str
    delete_measurement: str
    stimulus_queries: tuple[str, ...]
    data_query: str = "CALC{channel}:DATA? SDATA"

    def define(self, name: str, parameter: str, channel: int = 1) -> str:
        return self.define_measurement.format(
            name=name,
            parameter=parameter,
            channel=channel,
        )

    def select(self, name: str, channel: int = 1) -> str:
        return self.select_measurement.format(name=name, channel=channel)

    def delete(self, name: str, channel: int = 1) -> str:
        return self.delete_measurement.format(name=name, channel=channel)

    def data(self, channel: int = 1) -> str:
        return self.data_query.format(channel=channel)

    def stimulus(self, channel: int = 1) -> tuple[str, ...]:
        return tuple(command.format(channel=channel) for command in self.stimulus_queries)


PROFILES = {
    "GENERIC": ScpiProfile(
        key="GENERIC",
        display_name="Generic SCPI",
        define_measurement="CALC{channel}:PAR:DEF '{name}',{parameter}",
        select_measurement="CALC{channel}:PAR:SEL '{name}'",
        delete_measurement="CALC{channel}:PAR:DEL '{name}'",
        stimulus_queries=("SENS{channel}:FREQ:DATA?", "CALC{channel}:X?"),
    ),
    "KEYSIGHT": ScpiProfile(
        key="KEYSIGHT",
        display_name="Keysight PNA/ENA",
        define_measurement="CALC{channel}:PAR:DEF:EXT '{name}',{parameter}",
        select_measurement="CALC{channel}:PAR:SEL '{name}'",
        delete_measurement="CALC{channel}:PAR:DEL '{name}'",
        stimulus_queries=("SENS{channel}:FREQ:DATA?", "CALC{channel}:X?"),
    ),
    "ROHDE_SCHWARZ": ScpiProfile(
        key="ROHDE_SCHWARZ",
        display_name="Rohde & Schwarz ZNA/ZNB/ZND",
        define_measurement="CALC{channel}:PAR:SDEF '{name}','{parameter}'",
        select_measurement="CALC{channel}:PAR:SEL '{name}'",
        delete_measurement="CALC{channel}:PAR:DEL '{name}'",
        stimulus_queries=(
            "CALC{channel}:DATA:STIM?",
            "SENS{channel}:FREQ:DATA?",
            "CALC{channel}:X?",
        ),
        data_query="CALC{channel}:DATA? SDAT",
    ),
    "COPPER_MOUNTAIN": ScpiProfile(
        key="COPPER_MOUNTAIN",
        display_name="Copper Mountain",
        define_measurement="CALC{channel}:PAR:DEF '{name}',{parameter}",
        select_measurement="CALC{channel}:PAR:SEL '{name}'",
        delete_measurement="CALC{channel}:PAR:DEL '{name}'",
        stimulus_queries=("SENS{channel}:FREQ:DATA?", "CALC{channel}:X?"),
    ),
}


def select_profile(idn: str, requested: str | None = None) -> ScpiProfile:
    hint = (requested or "").strip().upper().replace("&", "").replace(" ", "_")
    aliases = {
        "KS": "KEYSIGHT",
        "AGILENT": "KEYSIGHT",
        "KEYSIGHT_TECHNOLOGIES": "KEYSIGHT",
        "RS": "ROHDE_SCHWARZ",
        "R_S": "ROHDE_SCHWARZ",
        "ROHDE__SCHWARZ": "ROHDE_SCHWARZ",
        "CMT": "COPPER_MOUNTAIN",
        "COPPERMOUNTAIN": "COPPER_MOUNTAIN",
    }
    hint = aliases.get(hint, hint)
    if hint in PROFILES:
        return PROFILES[hint]

    identity = idn.upper()
    if "KEYSIGHT" in identity or "AGILENT" in identity or "HEWLETT" in identity:
        return PROFILES["KEYSIGHT"]
    if "ROHDE" in identity or "SCHWARZ" in identity:
        return PROFILES["ROHDE_SCHWARZ"]
    if "COPPER MOUNTAIN" in identity or "CMT" in identity:
        return PROFILES["COPPER_MOUNTAIN"]
    return PROFILES["GENERIC"]
