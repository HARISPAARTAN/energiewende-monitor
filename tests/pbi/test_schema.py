"""Offline format checks: every PBIP/PBIR JSON file validates against its vendored $schema; TMDL smoke check."""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2]
PBI = ROOT / "powerbi"
TOOLS = ROOT / "tools" / "pbi"
SCHEMA_DIR = TOOLS / "schemas"
PREFIX = "https://developer.microsoft.com/json-schemas/"
VERSIONS = json.loads((TOOLS / "schema_versions.json").read_text(encoding="utf-8"))
TMDL_TOP = ("database", "model", "table", "relationship", "role", "expression", "cultureInfo", "perspective",
            "ref", "annotation", "dataSource", "queryGroup", "function", "///", "extendedProperty")
FENCE = "`" * 3  # TMDL verbatim-expression delimiter (spelled out so this file nests in Markdown fences)


def _local(uri: str) -> Path:
    assert uri.startswith(PREFIX), uri
    rel = uri[len(PREFIX):].split("#", 1)[0]
    # $id of the embedded variants reads schema.embedded.json while the file is schema-embedded.json
    return SCHEMA_DIR / rel.replace("schema.embedded.json", "schema-embedded.json")


def _retrieve(uri: str) -> Resource:
    return Resource.from_contents(json.loads(_local(uri).read_text(encoding="utf-8-sig")), default_specification=DRAFT7)


REGISTRY = Registry(retrieve=_retrieve)


def _validator(schema_uri: str) -> Draft7Validator:
    schema = json.loads(_local(schema_uri).read_text(encoding="utf-8-sig"))
    return Draft7Validator(schema, registry=REGISTRY)


def _project_json_files() -> list[Path]:
    files = [p for p in PBI.rglob("*") if p.is_file() and p.suffix in (".json", ".pbip", ".pbir", ".pbism")]
    return sorted(p for p in files if ".pbi" not in p.parts and "StaticResources" not in p.parts)


def _template_files() -> list[Path]:
    return sorted((TOOLS / "templates").glob("*.json"))


def _pinned() -> set[str]:
    out = set()
    for value in VERSIONS.values():
        if isinstance(value, str) and value.startswith(PREFIX):
            out.add(value)
        elif isinstance(value, dict) and str(value.get("$schema", "")).startswith(PREFIX):
            out.add(value["$schema"])
    return out


def test_project_exists():
    assert (PBI / "EnergiewendeMonitor.pbip").is_file()
    assert _project_json_files()


@pytest.mark.parametrize("path", _project_json_files() + _template_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_json_validates_against_pinned_schema(path):
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "UTF-8 without BOM required"
    data = json.loads(raw.decode("utf-8"))
    uri = data.get("$schema")
    assert uri, "every PBIP/PBIR JSON file carries $schema"
    if uri in VERSIONS.get("unpublished", []):
        pytest.skip(f"{uri} was written by Desktop but is not published in microsoft/json-schemas yet")
    assert uri in _pinned(), f"{uri} is not a pinned version (tools/pbi/schema_versions.json)"
    errors = sorted(_validator(uri).iter_errors(data), key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in errors[:10])


def test_templates_are_data_free():
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        assert "SourceRef" not in text and '"filterConfig"' not in text, path.name


def _tmdl_files() -> list[Path]:
    return sorted((PBI / "EnergiewendeMonitor.SemanticModel" / "definition").rglob("*.tmdl"))


@pytest.mark.parametrize("path", _tmdl_files(), ids=lambda p: p.name)
def test_tmdl_smoke(path):
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "UTF-8 without BOM required"
    text = raw.decode("utf-8")
    assert text.count(FENCE) % 2 == 0, "unbalanced triple-backtick expression block"
    prev = 0
    in_backticks = False
    for no, line in enumerate(text.splitlines(), 1):
        if line.count(FENCE) % 2:
            in_backticks = not in_backticks
        if in_backticks or not line.strip():
            continue
        assert not line.startswith(" "), f"line {no}: indentation must use tabs"
        indent = len(line) - len(line.lstrip("\t"))
        assert indent <= prev + 2, f"line {no}: indentation jumps from {prev} to {indent} tabs"
        if indent == 0:
            assert line.startswith(TMDL_TOP), f"line {no}: unexpected top-level token {line.split()[0]!r}"
        prev = indent
    if path.parent.name == "tables":
        decl = re.findall(r"^table (.+)$", text, flags=re.M)
        assert len(decl) == 1, "one table per file"
        name = decl[0].strip()
        name = name[1:-1].replace("''", "'") if name.startswith("'") else name
        assert name == path.stem, f"file {path.name} declares table {name!r}"


def test_model_refs_match_table_files():
    model = (PBI / "EnergiewendeMonitor.SemanticModel" / "definition" / "model.tmdl").read_text(encoding="utf-8")
    refs = {m.strip().strip("'").replace("''", "'") for m in re.findall(r"^ref table (.+)$", model, flags=re.M)}
    files = {p.stem for p in (PBI / "EnergiewendeMonitor.SemanticModel" / "definition" / "tables").glob("*.tmdl")}
    assert refs == files, (refs ^ files)


def test_partitions_use_the_rpt_views_only():
    for path in (PBI / "EnergiewendeMonitor.SemanticModel" / "definition" / "tables").glob("*.tmdl"):
        text = path.read_text(encoding="utf-8")
        for server, db in re.findall(r'Sql\.Database\("([^"]+)",\s*"([^"]+)"\)', text):
            assert (server, db) == ("127.0.0.1,1433", "energiewende"), path.name
        assert not re.search(r'Schema\s*=\s*"(stg|dw)"', text), path.name
        assert "password" not in text.lower(), path.name
