"""
Reads a Nix workout export (.xlsx) into one sweat session in our stored units.

An .xlsx is a zip of XML files, so this only needs the standard library. Rows and columns
are found by their labels, never by position, and the athlete's name is never read.
See docs/layer3_spec.md for the layout and the rules.
"""

from __future__ import annotations

import io
import math
import posixpath
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from layer3 import config as C

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

# Everything a broken zip or workbook can throw while being opened and read. Any of these
# means the file is damaged, and the person gets the plain message instead of a server error.
_BROKEN = (
    zipfile.BadZipFile,
    zlib.error,
    EOFError,
    struct.error,
    KeyError,
    IndexError,
    ET.ParseError,
    LookupError,
    ValueError,
    OverflowError,
    RuntimeError,
    NotImplementedError,
    OSError,
)


class NixFileError(ValueError):
    """The file can't be imported. The message is plain English and the app shows it as is."""


@dataclass
class NixMinute:
    minute: int
    sweat_rate_l_h: float | None
    respiration_rate_l_h: float | None
    total_fluid_ml: float | None
    electrolyte_rate_mg_h: float | None = None
    total_electrolytes_mg: float | None = None
    sodium_rate_mg_h: float | None = None
    total_sodium_mg: float | None = None


@dataclass
class NixSession:
    start_local: datetime  # phone's local time, no time zone in the file
    end_local: datetime
    unit_system: str  # metric or customary, the less precise one if a file mixes them
    fluid_loss_ml: float
    sweat_rate_l_h: float | None
    electrolytes_mg: float | None
    electrolyte_rate_mg_h: float | None
    sodium_mg: float | None
    sodium_rate_mg_h: float | None
    sweat_composition_mg_l: float | None
    nix_index: float | None
    workout_type: str | None
    sweat_detected: bool
    file_weight_kg: float | None  # only ever offered as a suggestion, never stored
    file_duration_min: float | None = None  # the Duration row, when it could be read
    warnings: list[str] = field(default_factory=list)
    minutes: list[NixMinute] = field(default_factory=list)


# ---------------------------------------------------------------- opening the workbook


def read_nix(source: bytes | bytearray | memoryview | str | Path) -> NixSession:
    """Read a Nix export from bytes or a path. Raises NixFileError with a message for the app."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        data = bytes(source)
    else:
        data = Path(source).read_bytes()
    sheets = _open_workbook(data)
    rows = _summary(sheets)
    minutes, systems = _timeseries(sheets)
    return _session(rows, minutes, systems)


Grid = dict[tuple[int, int], str]


def _open_workbook(data: bytes) -> dict[str, Grid]:
    """Every sheet as {(row, col): text}, keyed by its name in lower case."""
    if data[:5] == b"%PDF-":
        raise NixFileError(C.ERR_PDF)
    if data[:8] == C.OLE_SIGNATURE:
        raise NixFileError(C.ERR_PROTECTED)
    if not data.startswith(b"PK"):
        raise NixFileError(C.ERR_NOT_XLSX)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        infos = z.infolist()
        # First a quick check on the zip's own listing, so an honest zip bomb is refused before unpacking.
        if sum(i.file_size for i in infos) > C.MAX_UNZIPPED_BYTES:
            raise NixFileError(C.ERR_TOO_BIG)
        names = {i.filename for i in infos}
        if "xl/workbook.xml" not in names:
            raise NixFileError(C.ERR_NOT_XLSX)
        budget = [C.MAX_UNZIPPED_BYTES]  # bytes still allowed, counted while unpacking
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [_text_of(si) for si in _xml(z, "xl/sharedStrings.xml", budget).iter(NS + "si")]
        workbook = _xml(z, "xl/workbook.xml", budget)
        rels = _xml(z, "xl/_rels/workbook.xml.rels", budget)
        targets = {r.get("Id"): r.get("Target", "") for r in rels.iter(REL_NS + "Relationship")}
        sheets: dict[str, Grid] = {}
        for s in workbook.iter(NS + "sheet"):
            name = _clean(s.get("name", "")).lower()
            target = targets.get(s.get(REL_ID), "")
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            if name not in sheets and path in names:  # the first sheet with a name wins
                sheets[name] = _grid(_xml(z, path, budget), shared)
    except NixFileError:
        raise
    except _BROKEN as e:
        raise NixFileError(C.ERR_DAMAGED) from e
    return sheets


def _read(z: zipfile.ZipFile, name: str, budget: list[int]) -> bytes:
    """Unpack one part a chunk at a time. The listing can lie about sizes, the running count can't."""
    chunks = []
    with z.open(name) as f:
        while chunk := f.read(C.READ_CHUNK_BYTES):
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise NixFileError(C.ERR_TOO_BIG)
            chunks.append(chunk)
    return b"".join(chunks)


_DECLARED_ENCODING = re.compile(rb"\s*<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']*)[\"']")


def _xml(z: zipfile.ZipFile, name: str, budget: list[int]) -> ET.Element:
    raw = _read(z, name, budget)
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    # Excel only writes UTF-8. Other encodings (UTF-16 has zero bytes) could hide a DOCTYPE from the check below.
    declared = _DECLARED_ENCODING.match(raw)
    if b"\0" in raw or (declared and declared.group(1).decode("ascii", "replace").lower() not in C.XML_ENCODINGS):
        raise NixFileError(C.ERR_DAMAGED)
    # Excel never writes a DOCTYPE. Refusing it rules out entity tricks in a crafted file.
    if re.search(rb"<!DOCTYPE|<!ENTITY", raw, re.IGNORECASE):
        raise NixFileError(C.ERR_DAMAGED)
    return ET.fromstring(raw)


def _text_of(item: ET.Element) -> str:
    """Text of a shared string or an inline string. Phonetic hints (rPh) aren't part of the text."""
    t = item.find(NS + "t")
    if t is not None:
        return t.text or ""
    return "".join(r.text or "" for r in item.iterfind(f"{NS}r/{NS}t"))


_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _col(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _grid(root: ET.Element, shared: list[str]) -> Grid:
    """Cells with a value. The r attribute is optional in the format, so position is tracked too."""
    grid: Grid = {}
    row_no = 0
    for row in root.iter(NS + "row"):
        r = row.get("r")
        if r is not None and not (r.isascii() and r.isdigit()):
            raise NixFileError(C.ERR_DAMAGED)
        row_no = int(r) if r is not None else row_no + 1
        col_no = 0
        for c in row.iter(NS + "c"):
            m = _REF.match(c.get("r", ""))
            col_no = _col(m.group(1)) if m else col_no + 1
            kind = c.get("t")
            v = c.find(NS + "v")
            if kind == "inlineStr":
                item = c.find(NS + "is")
                text = _text_of(item) if item is not None else ""
            elif v is None or v.text is None:
                continue
            elif kind == "s":
                i = int(v.text)
                text = shared[i] if 0 <= i < len(shared) else ""
            else:
                text = v.text
            if len(text) > C.MAX_CELL_CHARS:
                raise NixFileError(C.ERR_LONG_CELL)
            grid[(row_no, col_no)] = text
    return grid


# ---------------------------------------------------------------- reading values

_INVISIBLE = re.compile("[​‌‍⁠﻿]")


def _clean(s: str) -> str:
    """Any kind of space (Nix puts a narrow no-break space before PM) becomes one plain space."""
    return re.sub(r"\s+", " ", _INVISIBLE.sub("", s)).strip()


def _short(s: str) -> str:
    """A bad value quoted back in a message, cut down so a junk cell can't make a huge message."""
    n = C.ERROR_VALUE_MAX_CHARS
    return s if len(s) <= n else s[:n] + "…"


_LABEL = re.compile(r"^(.*?)\s*(?:\(([^()]*)\))?$")


def _split_label(text: str) -> tuple[str, str | None]:
    """'Total Fluid Loss (oz)' -> ('total fluid loss', 'oz')."""
    m = _LABEL.match(_clean(text))
    name, unit = (m.group(1), m.group(2)) if m else (text, None)
    return name.strip().lower(), (unit.strip() if unit is not None else None)


def _unit_outside_brackets(name: str, fields: dict[str, str]) -> bool:
    """'total fluid loss ml' or 'total fluid loss [ml]': a field we know, with its unit written oddly."""
    for known, key in fields.items():
        if key in C.FIELD_KIND and key != "weight" and name.startswith(known) and name != known:
            rest = name[len(known) :].strip()
            if rest and " " not in rest and len(rest) <= 10:
                return True
    return False


# Plain digits only, as Nix writes them, with an optional decimal part and thousands commas (1,150).
_NUMBER = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+", re.ASCII)


def _number(raw: str | None, label: str) -> float | None:
    if raw is None:
        return None
    s = _clean(raw)
    if s in C.MISSING_TEXT:
        return None
    if s.startswith("-") and _NUMBER.fullmatch(s[1:].strip()):
        raise NixFileError(C.ERR_NEGATIVE.format(label=label, value=_short(s)))
    if not _NUMBER.fullmatch(s):
        raise NixFileError(C.ERR_BAD_NUMBER.format(label=label, value=_short(s)))
    x = float(s.replace(",", ""))
    if not math.isfinite(x):  # a few hundred digits overflow to infinity
        raise NixFileError(C.ERR_BAD_NUMBER.format(label=label, value=_short(s)))
    return x


def _factor(field_name: str, unit: str | None, label: str) -> float:
    factors = C.UNIT_FACTORS[C.FIELD_KIND[field_name]]
    key = (unit or "").lower().replace(" ", "")
    if key not in factors:
        raise NixFileError(C.ERR_UNKNOWN_UNIT.format(label=label))
    return factors[key]


def _converted(raw: str | None, field_name: str, unit: str | None, label: str) -> float | None:
    """A number in our stored unit, refused if it's far beyond what a workout can produce."""
    factor = _factor(field_name, unit, label)
    x = _number(raw, label)
    if x is None:
        return None
    y = x * factor
    shown = _short(_clean(raw or ""))
    if not math.isfinite(y):
        raise NixFileError(C.ERR_BAD_NUMBER.format(label=label, value=shown))
    if y > C.PLAUSIBLE_MAX[C.FIELD_KIND[field_name]]:
        raise NixFileError(C.ERR_IMPLAUSIBLE.format(label=label, value=shown))
    return y


_MONTHS = {
    name: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for name in names
}
# "Oct 25, 2026 at 2:55 PM" (export) and "May 27, 2025, 12:42 PM" (Nix guide). 24-hour times work too.
_DATE = re.compile(
    r"^([A-Za-z]+)\.? (\d{1,2}),? (\d{4})(?:,| at)? (\d{1,2}):(\d{2})(?::(\d{2}))?(?: ?([AaPp])\.? ?[Mm]\.?)?$",
    re.ASCII,
)
_EXCEL_EPOCH = datetime(1899, 12, 30)


def _date(raw: str, label: str) -> datetime:
    s = _clean(raw)
    when = None
    try:
        m = _DATE.match(s)
        if m:
            month = _MONTHS[m.group(1).lower()]
            hour, minute, second = int(m.group(4)), int(m.group(5)), int(m.group(6) or 0)
            if m.group(7):
                if not 1 <= hour <= 12:
                    raise ValueError
                hour = hour % 12 + (12 if m.group(7).lower() == "p" else 0)
            when = datetime(int(m.group(3)), month, int(m.group(2)), hour, minute, second)
        elif _NUMBER.fullmatch(s):
            # A real Excel date cell is a day count. Nix writes text, but a re-saved file might not.
            days = float(s)
            if days < 2_958_466:
                when = _EXCEL_EPOCH + timedelta(days=round(days * 86400) / 86400)
    except (KeyError, ValueError, OverflowError):
        when = None
    if when is None or when.year < C.EARLIEST_YEAR:
        raise NixFileError(C.ERR_BAD_DATE.format(label=label, value=_short(s)))
    return when


_DURATION = re.compile(r"(\d{1,3}):([0-5]\d):([0-5]\d)", re.ASCII)


def _duration_min(raw: str) -> float | None:
    """'02:12:54' -> 132.9. Anything else is None, and the caller falls back to end minus start."""
    m = _DURATION.fullmatch(_clean(raw))
    return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 60 if m else None


# ---------------------------------------------------------------- the two sheets


def _sheet(sheets: dict[str, Grid], name: str) -> Grid:
    grid = sheets.get(name.lower())
    if grid is None:
        raise NixFileError(C.ERR_MISSING_SHEET.format(sheet=name))
    return grid


def _find(grid: Grid, text: str, sheet: str) -> tuple[int, int]:
    """Top-most, left-most heading cell with this name ('Minutes (min)' counts as Minutes)."""
    hits = [rc for rc, v in grid.items() if _split_label(v)[0] == text.lower()]
    if not hits:
        raise NixFileError(C.ERR_MISSING_HEADER.format(sheet=sheet, header=text))
    return min(hits)


@dataclass
class _Row:
    label: str
    unit: str | None
    value: str | None


def _summary(sheets: dict[str, Grid]) -> dict[str, _Row]:
    grid = _sheet(sheets, C.SUMMARY_SHEET)
    r0, c0 = _find(grid, C.SUMMARY_HEADER, C.SUMMARY_SHEET)
    rows: dict[str, _Row] = {}
    # Only rows that have a label, so a stray cell far down the sheet costs nothing.
    for r in sorted(r for (r, c) in grid if c == c0 and r > r0):
        label = grid[(r, c0)]
        if not label:
            continue
        name, unit = _split_label(label)
        key = C.SUMMARY_FIELDS.get(name)
        if key is None and _unit_outside_brackets(name, C.SUMMARY_FIELDS):
            raise NixFileError(C.ERR_UNKNOWN_UNIT.format(label=_clean(label)))
        if key and key not in rows:  # the first row with a label wins
            rows[key] = _Row(_clean(label), unit, grid.get((r, c0 + 1)))
    for key, label in C.REQUIRED_SUMMARY.items():
        row = rows.get(key)
        if row is None or row.value is None or _clean(row.value) in C.MISSING_TEXT:
            raise NixFileError(C.ERR_MISSING_ROW.format(label=label))
    return rows


def _timeseries(sheets: dict[str, Grid]) -> tuple[list[NixMinute], set[str]]:
    """The minute rows, plus which unit settings (metric, customary) their headings use."""
    grid = _sheet(sheets, C.TIMESERIES_SHEET)
    r0, c0 = _find(grid, C.TIMESERIES_HEADER, C.TIMESERIES_SHEET)
    cols: dict[str, tuple[int, str, str | None]] = {}  # field -> (column, label, unit)
    for (r, c), text in sorted(grid.items()):
        if r != r0 or c < c0:
            continue
        name, unit = _split_label(text)
        key = C.TIMESERIES_FIELDS.get(name)
        if key is None and _unit_outside_brackets(name, C.TIMESERIES_FIELDS):
            raise NixFileError(C.ERR_UNKNOWN_UNIT.format(label=_clean(text)))
        if key and key not in cols:
            cols[key] = (c, _clean(text), unit)
    for key, label in C.REQUIRED_TIMESERIES.items():
        if key not in cols:
            raise NixFileError(C.ERR_MISSING_COLUMN.format(sheet=C.TIMESERIES_SHEET, label=label))
    for key, (_c, label, unit) in cols.items():
        if key != "minute":
            _factor(key, unit, label)  # an unknown unit is refused even when every cell is empty
    units = {(unit or "").lower().replace(" ", "") for _c, _l, unit in cols.values()}
    systems = {C.UNIT_SYSTEM[u] for u in units if u in C.UNIT_SYSTEM}

    out = []
    r = r0 + 1
    while True:  # stops at the first empty Minutes cell, the formatted rows after it are blank
        raw_minute = grid.get((r, c0))
        if raw_minute is None or _clean(raw_minute) in C.MISSING_TEXT:
            break
        minute = _number(raw_minute, "Minutes")
        if minute is None or minute > C.MAX_MINUTES or minute != int(minute):
            raise NixFileError(C.ERR_BAD_NUMBER.format(label="Minutes", value=_short(_clean(raw_minute))))
        values = {
            key: _converted(grid.get((r, c)), key, unit, label)
            for key, (c, label, unit) in cols.items()
            if key != "minute"
        }
        out.append(
            NixMinute(
                minute=int(minute),
                sweat_rate_l_h=values.get("sweat_rate"),
                respiration_rate_l_h=values.get("respiration_rate"),
                total_fluid_ml=values.get("total_fluid"),
                electrolyte_rate_mg_h=values.get("electrolyte_rate"),
                total_electrolytes_mg=values.get("total_electrolytes"),
                sodium_rate_mg_h=values.get("sodium_rate"),
                total_sodium_mg=values.get("total_sodium"),
            )
        )
        r += 1
    return out, systems


# ---------------------------------------------------------------- putting the session together


def _value(rows: dict[str, _Row], key: str) -> float | None:
    """A summary number converted to our unit, or None when the row is missing or empty."""
    row = rows.get(key)
    return None if row is None else _converted(row.value, key, row.unit, row.label)


def _weight_suggestion(rows: dict[str, _Row]) -> float | None:
    """Weight isn't needed for the import, so anything odd just means no suggestion."""
    try:
        kg = _value(rows, "weight")
    except NixFileError:
        return None
    lo, hi = C.WEIGHT_RANGE_KG
    return round(kg, 1) if kg is not None and lo <= kg <= hi else None


def _nix_index(rows: dict[str, _Row]) -> float | None:
    """Nix Index isn't needed either, so an odd one is just left out."""
    row = rows.get("nix_index")
    try:
        return _number(row.value, row.label) if row else None
    except NixFileError:
        return None


def _text(rows: dict[str, _Row], key: str) -> str | None:
    row = rows.get(key)
    s = _clean(row.value) if row and row.value else ""
    return s[:60] if s and s not in C.MISSING_TEXT else None


def _sweaty(m: NixMinute) -> bool:
    """Did Nix read sweat in this minute, beyond breathing loss and rounding?"""
    if m.sweat_rate_l_h is None:
        return False
    if m.respiration_rate_l_h is None:
        return m.sweat_rate_l_h > C.SWEAT_RATE_CLEARLY_L_H
    return m.sweat_rate_l_h - m.respiration_rate_l_h > C.SWEAT_ABOVE_RESPIRATION_L_H


def _session(rows: dict[str, _Row], minutes: list[NixMinute], ts_systems: set[str]) -> NixSession:
    start = _date(rows["start"].value or "", "start time")
    end = _date(rows["end"].value or "", "end time")
    if start - end >= timedelta(minutes=C.DST_BACKWARD_MAX_MIN):
        raise NixFileError(C.ERR_END_BEFORE_START)
    span_min = (end - start).total_seconds() / 60

    fluid = _value(rows, "fluid_loss")
    assert fluid is not None  # required, checked in _summary
    sweat_rate = _value(rows, "sweat_rate")
    electrolytes = _value(rows, "electrolytes")
    sodium = _value(rows, "sodium")
    extras = {k: _value(rows, k) for k in ("electrolyte_rate", "sodium_rate", "sweat_composition")}
    units = {(row.unit or "").lower().replace(" ", "") for row in rows.values()}
    systems = ts_systems | {C.UNIT_SYSTEM[u] for u in units if u in C.UNIT_SYSTEM}
    unit_system = min(systems, key=C.UNIT_PRECISION.__getitem__)

    warnings = []
    duration_row = rows.get("duration")
    duration_raw = duration_row.value if duration_row else None
    duration = None
    if duration_raw is not None and _clean(duration_raw) not in C.MISSING_TEXT:
        duration = _duration_min(duration_raw)
        if duration is None:
            warnings.append(C.WARN_DURATION_UNREADABLE.format(value=_short(_clean(duration_raw))))
    # A Duration far from the times is a broken file, so the checks below use the times, like the server.
    used_min = span_min
    if duration is not None and abs(duration - span_min) > C.DURATION_CHECK_TOLERANCE_MIN:
        warnings.append(C.WARN_DURATION_MISMATCH.format(duration=duration, span=span_min))
    elif duration is not None:
        used_min = duration
    if sweat_rate is not None:
        expected = sweat_rate * 1000 * used_min / 60
        if abs(fluid - expected) > max(C.FLUID_CHECK_TOLERANCE * expected, C.FLUID_CHECK_ABS_ML):
            warnings.append(C.WARN_FLUID_MISMATCH.format(fluid=fluid, expected=expected))
    if abs(len(minutes) - used_min) > C.MINUTES_CHECK_TOLERANCE:
        warnings.append(C.WARN_MINUTES_MISMATCH.format(rows=len(minutes), minutes=used_min))

    # No sweat: the sweat rate never rises above breathing loss and no salt was lost.
    sweat_detected = any(_sweaty(m) for m in minutes) or any(x for x in (electrolytes, sodium))
    if not sweat_detected:
        # Zeros here would read as "lost no sodium", but Nix just didn't measure any. Keep them missing.
        electrolytes = sodium = None
        extras = dict.fromkeys(extras)
        for m in minutes:
            m.electrolyte_rate_mg_h = m.total_electrolytes_mg = m.sodium_rate_mg_h = m.total_sodium_mg = None
        warnings.append(C.WARN_NO_SWEAT)

    return NixSession(
        start_local=start,
        end_local=end,
        unit_system=unit_system,
        fluid_loss_ml=fluid,
        sweat_rate_l_h=sweat_rate,
        electrolytes_mg=electrolytes,
        electrolyte_rate_mg_h=extras["electrolyte_rate"],
        sodium_mg=sodium,
        sodium_rate_mg_h=extras["sodium_rate"],
        sweat_composition_mg_l=extras["sweat_composition"],
        nix_index=_nix_index(rows),
        workout_type=_text(rows, "workout_type") or _text(rows, "activity_type"),
        sweat_detected=sweat_detected,
        file_weight_kg=_weight_suggestion(rows),
        file_duration_min=duration,
        warnings=warnings,
        minutes=minutes,
    )
