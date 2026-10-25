"""Build the public variant of the Power BI project: the same model and report without the RLS role.

    uv run python tools/pbi/make_public_variant.py [SRC_PBIP] [OUT_DIR]

Defaults: powerbi/EnergiewendeMonitor.pbip to build/public/. The copy is renamed to
"EnergiewendeMonitor (öffentlich)" (.pbip, .SemanticModel, .Report), the paths inside the .pbip and
definition.pbir follow the rename, definition/roles/ and the `ref role` lines in model.tmdl are removed, and
build/public/README.txt says what the copy is for. Tables, relationships, measures and report pages are copied
byte for byte. Desktop's local files (.pbi/) are not copied.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUFFIX = " (öffentlich)"

README = """Energiewende-Monitor, öffentliche Variante

Diese Kopie des Power-BI-Projekts enthält keine Zeilensicherheit (RLS): Die Rolle "Landesbehörde BW" ist
entfernt. Modell und Bericht sind sonst unverändert (Tabellen, Beziehungen, Kennzahlen, Seiten).
Diese Variante wird per "Im Web veröffentlichen" (Publish to web) freigegeben, weil sie nur öffentliche,
aggregierte Daten (SMARD, Bundesnetzagentur | SMARD.de, und Marktstammdatenregister) enthält.

Erzeugt mit: uv run python tools/pbi/make_public_variant.py
Das Hauptprojekt unter powerbi/ behält die Rolle für Demonstrationen der Zeilensicherheit.
"""

README_EN = """Energiewende-Monitor, public variant

This copy of the Power BI project has no row-level security: the role "Landesbehörde BW" is removed. The model
and report are otherwise unchanged (tables, relationships, measures, pages). This is the copy that is published
to web, because it holds only public, aggregated data (SMARD, Bundesnetzagentur | SMARD.de, and the
Marktstammdatenregister).
"""


def _rewrite(path: Path, replacements: dict[str, str]) -> None:
    text = path.read_bytes().decode("utf-8")
    for old, new in replacements.items():
        if old not in text:
            raise ValueError(f"{path.name}: expected to find {old!r}")
        text = text.replace(old, new)
    path.write_bytes(text.encode("utf-8"))


def _drop_role_lines(path: Path) -> None:
    lines = path.read_bytes().decode("utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if not ln.lstrip().startswith("ref role")]
    path.write_bytes("".join(kept).encode("utf-8"))


def build(src_pbip: Path, out_dir: Path) -> Path:
    """Copy the PBIP next to renamed names into out_dir (created if needed) and return the new .pbip path."""
    src_pbip, out_dir = Path(src_pbip), Path(out_dir)
    base = src_pbip.stem
    new = base + SUFFIX
    src_model, src_report = src_pbip.parent / f"{base}.SemanticModel", src_pbip.parent / f"{base}.Report"
    if not (src_pbip.is_file() and src_model.is_dir() and src_report.is_dir()):
        raise FileNotFoundError(f"{src_pbip}, {src_model} and {src_report} must all exist")

    out_dir.mkdir(parents=True, exist_ok=True)
    dst_pbip, dst_model, dst_report = out_dir / f"{new}.pbip", out_dir / f"{new}.SemanticModel", out_dir / f"{new}.Report"
    for old in (dst_pbip, dst_model, dst_report, out_dir / "README.txt"):  # only our own previous output
        if old.is_dir():
            shutil.rmtree(old)
        elif old.exists():
            old.unlink()

    ignore = shutil.ignore_patterns(".pbi")
    shutil.copytree(src_model, dst_model, ignore=ignore)
    shutil.copytree(src_report, dst_report, ignore=ignore)
    shutil.copyfile(src_pbip, dst_pbip)

    _rewrite(dst_pbip, {f"{base}.Report": f"{new}.Report"})
    _rewrite(dst_report / "definition.pbir", {f"{base}.SemanticModel": f"{new}.SemanticModel"})
    shutil.rmtree(dst_model / "definition" / "roles", ignore_errors=True)
    _drop_role_lines(dst_model / "definition" / "model.tmdl")
    (out_dir / "README.txt").write_text(README + "\n" + README_EN, encoding="utf-8")
    return dst_pbip


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    src = Path(args[0]) if args else ROOT / "powerbi" / "EnergiewendeMonitor.pbip"
    out = Path(args[1]) if len(args) > 1 else ROOT / "build" / "public"
    print(build(src, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
