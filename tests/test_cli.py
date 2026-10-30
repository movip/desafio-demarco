import hashlib
import json
import sys
from pathlib import Path

from demarco.cli import main

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def test_cli_generates_reproducible_artifacts_without_changing_excel(tmp_path, monkeypatch):
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.glob("*.xlsx")}
    output = tmp_path / "diagnostico"
    monkeypatch.setattr(
        sys, "argv", ["demarco", "diagnose", "--input-dir", str(RAW), "--output-dir", str(output)]
    )
    assert main() == 0
    first = {p.name: p.read_bytes() for p in output.iterdir()}
    assert len(first) == 6
    assert main() == 0
    assert first == {p.name: p.read_bytes() for p in output.iterdir()}
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.glob("*.xlsx")
    }
    report = json.loads(first["quality.json"])
    assert report["tables"]["gestao"]["sha256"] == before["template_acoes_disciplinares.xlsx"]


def test_missing_input_stops_before_creating_output(tmp_path, monkeypatch):
    output = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        ["demarco", "diagnose", "--input-dir", str(tmp_path), "--output-dir", str(output)],
    )
    assert main() == 1
    assert not output.exists()


def test_output_cannot_be_inside_inputs(tmp_path, monkeypatch):
    output = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        ["demarco", "diagnose", "--input-dir", str(tmp_path), "--output-dir", str(output)],
    )
    assert main() == 1
    assert not output.exists()
