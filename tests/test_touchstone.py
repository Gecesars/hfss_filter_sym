from hfss_vna_bridge.adapters.vna.simulated import SimulatedVnaAdapter
from hfss_vna_bridge.core.models import SweepConfig


def test_simulated_vna_writes_s2p(tmp_path) -> None:
    vna = SimulatedVnaAdapter()
    vna.connect()
    vna.configure_sweep(SweepConfig(points=5))

    output = vna.save_touchstone(tmp_path / "trace.s2p")

    text = output.read_text(encoding="ascii")
    assert "# Hz S RI R 50" in text
    assert len([line for line in text.splitlines() if line and not line.startswith(("!", "#"))]) == 5

