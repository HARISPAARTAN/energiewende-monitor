import json
from pathlib import Path

import pytest

from tools.pbi import make_public_variant

pytestmark = pytest.mark.pbi
SRC = Path(__file__).resolve().parents[2] / "powerbi" / "EnergiewendeMonitor.pbip"
NAME = "EnergiewendeMonitor (öffentlich)"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("public")
    return out, make_public_variant.build(SRC, out)


def test_artefacts_are_renamed(built):
    out, pbip = built
    assert pbip == out / f"{NAME}.pbip"
    assert (out / f"{NAME}.SemanticModel" / "definition.pbism").is_file()
    assert (out / f"{NAME}.Report" / "definition.pbir").is_file()
    assert not (out / "EnergiewendeMonitor.pbip").exists()
    assert "keine Zeilensicherheit" in (out / "README.txt").read_text(encoding="utf-8")


def test_no_roles_left(built):
    out, _ = built
    model = out / f"{NAME}.SemanticModel" / "definition"
    assert not (model / "roles").exists()
    assert "role" not in (model / "model.tmdl").read_text(encoding="utf-8")
    assert not any("Landesbehörde" in p.read_text(encoding="utf-8") for p in model.rglob("*.tmdl"))


def test_pbip_and_pbir_point_at_the_renamed_folders(built):
    out, pbip = built
    artifacts = json.loads(pbip.read_text(encoding="utf-8"))["artifacts"]
    assert artifacts == [{"report": {"path": f"{NAME}.Report"}}]
    pbir = json.loads((out / f"{NAME}.Report" / "definition.pbir").read_text(encoding="utf-8"))
    target = pbir["datasetReference"]["byPath"]["path"]
    assert target == f"../{NAME}.SemanticModel"
    assert ((out / f"{NAME}.Report") / target).resolve().is_dir()


def test_tables_and_report_are_byte_identical(built):
    out, _ = built
    src_model = SRC.parent / "EnergiewendeMonitor.SemanticModel" / "definition"
    dst_model = out / f"{NAME}.SemanticModel" / "definition"
    for src in (src_model / "tables").glob("*.tmdl"):
        assert (dst_model / "tables" / src.name).read_bytes() == src.read_bytes(), src.name
    for name in ("relationships.tmdl", "database.tmdl"):
        assert (dst_model / name).read_bytes() == (src_model / name).read_bytes(), name
    assert sorted(p.name for p in (dst_model / "tables").glob("*.tmdl")) == sorted(p.name for p in (src_model / "tables").glob("*.tmdl"))
    src_report = SRC.parent / "EnergiewendeMonitor.Report" / "definition"
    for src in src_report.rglob("*.json"):
        dst = out / f"{NAME}.Report" / "definition" / src.relative_to(src_report)
        assert dst.read_bytes() == src.read_bytes(), src.name


def test_model_tmdl_differs_only_by_the_role_reference(built):
    out, _ = built
    src = (SRC.parent / "EnergiewendeMonitor.SemanticModel" / "definition" / "model.tmdl").read_text(encoding="utf-8").splitlines()
    dst = (out / f"{NAME}.SemanticModel" / "definition" / "model.tmdl").read_text(encoding="utf-8").splitlines()
    assert [ln for ln in src if not ln.startswith("ref role")] == dst
    assert len(src) - len(dst) == 1


def test_build_twice_into_the_same_folder(built):
    out, _ = built
    again = make_public_variant.build(SRC, out)
    assert again.is_file()
