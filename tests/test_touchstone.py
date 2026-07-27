from hfss_vna_bridge.adapters.vna.simulated import SimulatedVnaAdapter
from hfss_vna_bridge.core.models import SweepConfig
from hfss_vna_bridge.core.touchstone import compare_networks, read_s2p


def test_simulated_vna_writes_s2p(tmp_path) -> None:
    vna = SimulatedVnaAdapter()
    vna.connect()
    vna.configure_sweep(SweepConfig(points=5))

    output = vna.save_touchstone(tmp_path / "trace.s2p")

    text = output.read_text(encoding="ascii")
    assert "# Hz S RI R 50" in text
    assert len([line for line in text.splitlines() if line and not line.startswith(("!", "#"))]) == 5


def test_touchstone_reader_supports_ri_ma_and_db(tmp_path) -> None:
    files = {
        "ri.s2p": "# GHz S RI R 50\n1 0.1 0 0.8 0 0.8 0 0.1 0\n2 0.2 0 0.7 0 0.7 0 0.2 0\n",
        "ma.s2p": "# MHz S MA R 75\n1000 0.1 0 0.8 0 0.8 0 0.1 0\n2000 0.2 0 0.7 0 0.7 0 0.2 0\n",
        "db.s2p": "# Hz S DB R 50\n1000000000 -20 0 -1.9382 0 -1.9382 0 -20 0\n2000000000 -13.9794 0 -3.098 0 -3.098 0 -13.9794 0\n",
    }
    parsed = []
    for name, content in files.items():
        path = tmp_path / name
        path.write_text(content, encoding="ascii")
        parsed.append(read_s2p(path))

    assert all(len(data.points) == 2 for data in parsed)
    assert parsed[1].reference_ohm == 75
    assert parsed[0].points[0].freq_hz == parsed[1].points[0].freq_hz
    comparison = compare_networks(parsed[0].points, parsed[1].points)
    assert comparison["errors"]["s21"]["rmse_db"] < 1e-12
