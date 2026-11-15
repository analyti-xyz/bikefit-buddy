#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pytest",
#     "typer",
#     "rich",
#     "pyyaml",
# ]
# ///

import importlib.util
from pathlib import Path

import pytest
import yaml

spec = importlib.util.spec_from_file_location("bikefit", Path(__file__).with_name("bikefit.py"))
bikefit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bikefit)

TOLERANCE_MM = 1

# Stubs of the (gitignored) rider profiles the known reports were generated from
PROFILES = {
    "john_doe": {"inseam": 925.0, "torso": 601.0, "arm": 728.0},
    "jane_doe": {"inseam": 870.0, "torso": 540.0, "arm": 684.0},
}

# Known reports: (profile, bar, crank) -> saddle (X, Y), default handlebar (X, Y)
KNOWN_REPORTS = [
    ("john_doe", "drop", 175.0, (232, 784), (467, 734)),
    ("jane_doe", "drop", 172.5, (216, 729), (450, 687)),
]


@pytest.fixture
def profile_dir(tmp_path, monkeypatch):
    for name, data in PROFILES.items():
        (tmp_path / f"{name}.yml").write_text(yaml.safe_dump(data, sort_keys=False))
    monkeypatch.setattr(bikefit, "PROFILES_DIR", tmp_path)
    return tmp_path


@pytest.mark.parametrize("name, bar, crank, saddle, handlebar", KNOWN_REPORTS)
def test_known_report(profile_dir, name, bar, crank, saddle, handlebar):
    data = bikefit.load_profile(name)
    res = bikefit.compute_fit_model(
        inseam=data["inseam"], torso=data["torso"], arm=data["arm"], bar=bar, crank=crank
    )
    default_pt = res["grid"][(3, 3)]

    assert res["saddle_x"] == pytest.approx(saddle[0], abs=TOLERANCE_MM)
    assert res["saddle_y"] == pytest.approx(saddle[1], abs=TOLERANCE_MM)
    assert default_pt["bar_x"] == pytest.approx(handlebar[0], abs=TOLERANCE_MM)
    assert default_pt["bar_y"] == pytest.approx(handlebar[1], abs=TOLERANCE_MM)


@pytest.mark.parametrize("name, crank", [("john_doe", 175.0), ("jane_doe", 172.5)])
def test_default_crank(name, crank):
    assert bikefit.default_crank(PROFILES[name]["inseam"]) == crank


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
