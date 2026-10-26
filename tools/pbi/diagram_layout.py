"""Write the model diagram of the project (EnergiewendeMonitor.SemanticModel/diagramLayout.json).

Dimensions in the top row, facts below them, the tables without relationships in a third row: every relationship line runs in
the gap between the first two rows and none crosses a table (Desktop's automatic layout drew lines through tables). Desktop
rewrites the file when it saves the project; from then on the layout is kept in Desktop.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

MODEL = Path(__file__).resolve().parents[2] / "powerbi" / "EnergiewendeMonitor.SemanticModel"
ROWS = [
    ["Zeit", "Region", "Datum", "Energieträger", "Bundesland"],
    ["Preis", "Last", "Last Stunde", "Preisphasen", "Erzeugung", "Kapazität"],
    ["Kennzahlen", "Kennzahl-Auswahl", "Datenlücken"],
]
WIDTH, HEIGHT, GAP_X, GAP_Y = 234, 280, 60, 150  # node size and gaps in diagram units; zoom 70 % shows all three rows


def layout(model: Path = MODEL) -> dict:
    tables = {p.stem for p in (model / "definition" / "tables").glob("*.tmdl")}
    placed = [name for row in ROWS for name in row]
    if sorted(placed) != sorted(tables):
        raise ValueError(f"the rows must place every table once: {sorted(set(placed) ^ tables)}")
    widest = max(len(row) for row in ROWS) * (WIDTH + GAP_X) - GAP_X
    nodes = []
    for i, row in enumerate(ROWS):
        left = (widest - (len(row) * (WIDTH + GAP_X) - GAP_X)) / 2  # rows centred under each other
        for j, name in enumerate(row):
            tmdl = (model / "definition" / "tables" / f"{name}.tmdl").read_text(encoding="utf-8")
            nodes.append({"location": {"x": left + j * (WIDTH + GAP_X), "y": i * (HEIGHT + GAP_Y)}, "nodeIndex": name,
                          "nodeLineageTag": re.search(r"^\tlineageTag: (\S+)", tmdl, re.M).group(1),
                          "size": {"height": HEIGHT, "width": WIDTH}, "zIndex": len(nodes)})
    diagram = {"ordinal": 0, "scrollPosition": {"x": 0, "y": 0}, "nodes": nodes, "name": "All tables", "zoomValue": 70,
               "pinKeyFieldsToTop": False, "showExtraHeaderInfo": False, "hideKeyFieldsWhenCollapsed": False, "tablesLocked": False}
    return {"version": "1.1.0", "diagrams": [diagram], "selectedDiagram": "All tables", "defaultDiagram": "All tables"}


def main() -> None:
    path = MODEL / "diagramLayout.json"
    path.write_text(json.dumps(layout(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
