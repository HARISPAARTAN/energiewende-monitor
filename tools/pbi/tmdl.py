"""Minimal TMDL reader for linting: tables, columns, measures, partitions, relationships, roles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Column:
    name: str
    data_type: str | None = None
    is_hidden: bool = False
    is_key: bool = False
    format_string: str | None = None
    summarize_by: str | None = None


@dataclass
class Measure:
    name: str
    expression: str
    format_string: str | None = None
    description: str | None = None


@dataclass
class Table:
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    measures: dict[str, Measure] = field(default_factory=dict)
    data_category: str | None = None
    partition_source: str | None = None
    raw: str | None = None


@dataclass
class Relationship:
    name: str
    from_column: str  # "Table.Column", both parts unquoted
    to_column: str
    cross_filtering_behavior: str | None = None


@dataclass
class Role:
    name: str
    table_permissions: dict[str, str] = field(default_factory=dict)


@dataclass
class Model:
    tables: dict[str, Table]
    relationships: list[Relationship]
    roles: list[Role]


def _unquote(name: str) -> str:
    name = name.strip()
    return name[1:-1].replace("''", "'") if name.startswith("'") and name.endswith("'") else name


def _qualified(ref: str | None) -> str:
    """`Table.'Column name'` or `'Table name'.'Column name'` -> `Table.Column name` (names unquoted)."""
    m = re.fullmatch(r"\s*('(?:[^']|'')+'|[^.\s']+)\.('(?:[^']|'')+'|[^.\s']+)\s*", ref or "")
    return f"{_unquote(m.group(1))}.{_unquote(m.group(2))}" if m else (ref or "")


def _descriptions(text: str) -> dict[str, str]:
    """Map measure/column/table names to their /// description (the lines directly above the declaration)."""
    out: dict[str, str] = {}
    pending: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("///"):
            pending.append(s[3:].strip())
            continue
        if pending:
            m = re.match(r"(?:measure|column|table)\s+('(?:[^']|'')+'|[^\s=]+)", s)
            if m:
                out[_unquote(m.group(1))] = " ".join(pending)
        pending = []
    return out


def _blocks(text: str, keyword: str):
    """Yield (name, expression_on_first_line, body_lines, indent) for `keyword name` blocks."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip("\t")
        indent = len(line) - len(stripped)
        if stripped.startswith(keyword + " ") or stripped.startswith(keyword + "\t"):
            head = stripped[len(keyword):].strip()
            m = re.match(r"(.*?)\s=(?:\s(.*)|$)", head)  # `name = expr` or `name =` (expression on next lines)
            name, expr_first = (m.group(1), m.group(2)) if m else (head, None)
            body = []
            j = i + 1
            while j < len(lines) and (lines[j].strip() == "" or (len(lines[j]) - len(lines[j].lstrip("\t"))) > indent):
                body.append(lines[j][indent + 1:] if lines[j].strip() else "")
                j += 1
            yield _unquote(name), expr_first, body, indent
            i = j
        else:
            i += 1


def _prop(body: list[str], key: str) -> str | None:
    """A property of the object itself: only lines at the body's first indent level (nested objects are skipped)."""
    for line in body:
        if line.startswith("\t"):
            continue
        s = line.strip()
        if s.startswith(key + ":"):
            return s.split(":", 1)[1].strip()
        if s == key:
            return "true"
    return None


def _partition_source(body: list[str]) -> str:
    """The `source =` expression of a partition (body lines are relative: properties at 0 tabs, expression deeper)."""
    out: list[str] = []
    on = False
    for line in body:
        s = line.strip()
        if not on:
            if s.startswith("source ="):
                rest = s.split("=", 1)[1].strip()
                if rest:
                    return rest
                on = True
            continue
        if line.startswith("\t"):
            out.append(s)
        elif s == "":
            continue
        else:
            break
    return "\n".join(out)


def _measure_expression(first: str | None, body: list[str]) -> str:
    if first is not None and first.strip():
        return first.strip()
    out = []
    for line in body:
        if line.strip() == "":
            continue
        if re.match(r"^\s*(formatString|description|lineageTag|displayFolder|annotation|isHidden|changedProperty|extendedProperty)\b", line):
            break
        out.append(line.strip())
    return "\n".join(out)


def load_model(definition_dir: Path) -> Model:
    tables = {}
    for path in sorted((Path(definition_dir) / "tables").glob("*.tmdl")):
        text = path.read_text(encoding="utf-8")
        descs = _descriptions(text)
        for tname, _, tbody, _ in _blocks(text, "table"):
            t = Table(tname, raw=text, data_category=_prop(tbody, "dataCategory"))
            inner = "\n".join(tbody)
            for cname, _cfirst, cbody, _ in _blocks(inner, "column"):
                t.columns[cname] = Column(
                    cname,
                    _prop(cbody, "dataType"),
                    _prop(cbody, "isHidden") == "true",
                    _prop(cbody, "isKey") == "true",
                    _prop(cbody, "formatString"),
                    _prop(cbody, "summarizeBy"),
                )
            for mname, mfirst, mbody, _ in _blocks(inner, "measure"):
                t.measures[mname] = Measure(mname, _measure_expression(mfirst, mbody), _prop(mbody, "formatString"), descs.get(mname))
            for _pname, _pfirst, pbody, _ in _blocks(inner, "partition"):
                t.partition_source = _partition_source(pbody)
            tables[tname] = t
    rels = []
    rel_path = Path(definition_dir) / "relationships.tmdl"
    if rel_path.exists():
        for rname, _, rbody, _ in _blocks(rel_path.read_text(encoding="utf-8"), "relationship"):
            rels.append(Relationship(rname, _qualified(_prop(rbody, "fromColumn")), _qualified(_prop(rbody, "toColumn")), _prop(rbody, "crossFilteringBehavior")))
    roles = []
    for path in sorted((Path(definition_dir) / "roles").glob("*.tmdl")) if (Path(definition_dir) / "roles").exists() else []:
        text = path.read_text(encoding="utf-8")
        for rname, _, rbody, _ in _blocks(text, "role"):
            role = Role(rname)
            for line in rbody:
                m = re.match(r"\s*tablePermission\s+('(?:[^']|'')+'|[^\s=]+)\s*=\s*(.+)$", line)
                if m:
                    role.table_permissions[_unquote(m.group(1))] = m.group(2).strip()
            roles.append(role)
    return Model(tables, rels, roles)
