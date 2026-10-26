"""
Fake Nix exports for tests and demos, built to copy the real export's layout exactly
(two sheets, tables at B2, numbers stored as text, empty formatted rows after the data).

The real exports have a person's name and body details, so they never go in the repo.
These use made-up numbers worked out from known totals, so the tests know the right answer.

    cd preprocessing
    python -m layer3.samples        rewrites sample_data/layer3/
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from layer3.config import OZ_TO_ML

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "layer3"
FAKE_ATHLETE = "Test Athlete"
NNBSP = " "  # Nix puts this narrow space before AM and PM

Cell = str | int | float  # str is written as text (like most Nix numbers), int and float as real numbers


# ---------------------------------------------------------------- the made-up workouts


@dataclass
class Truth:
    """What a fake workout really was, in metric, minute by minute."""

    start: str
    end: str
    duration: str
    minutes: int
    workout_type: str
    nix_index: int
    respiration_ml_h: list[float]
    sweat_ml_h: list[float]  # includes breathing, like Nix's Sweat Rate column
    sodium_mg_h: list[float]
    electrolyte_mg_h: list[float]
    weight_kg: int
    weight_lb: int
    height_cm: int
    height_ft: str

    def total_fluid_ml(self, upto: int | None = None) -> float:
        return sum(r / 60 for r in self.sweat_ml_h[:upto])

    def total_mg(self, rates: list[float], upto: int | None = None) -> float:
        return sum(r / 60 for r in rates[:upto])


def no_sweat_workout() -> Truth:
    """Like the real exports: a cool gym, sweat never rose above breathing, no salt at all."""
    rates = [28.0] * 132 + [25.2]
    return Truth(
        start=f"Oct 25, 2026 at 2:55{NNBSP}PM",
        end=f"Oct 25, 2026 at 5:08{NNBSP}PM",
        duration="02:12:54",
        minutes=133,
        workout_type="Weightlifting",
        nix_index=59,
        respiration_ml_h=rates,
        sweat_ml_h=rates,
        sodium_mg_h=[0.0] * 133,
        electrolyte_mg_h=[0.0] * 133,
        weight_kg=73,
        weight_lb=162,
        height_cm=175,
        height_ft="5' 9\"",
    )


def sweat_workout() -> Truth:
    """A one-hour run: Nix picks up sweat after 15 minutes, then 900 ml/h and real sodium."""
    n, lag = 60, 15
    return Truth(
        start=f"Oct 20, 2026 at 6:00{NNBSP}PM",
        end=f"Oct 20, 2026 at 7:00{NNBSP}PM",
        duration="01:00:00",
        minutes=n,
        workout_type="Running",
        nix_index=74,
        respiration_ml_h=[30.0] * n,
        sweat_ml_h=[30.0] * lag + [900.0] * (n - lag),
        sodium_mg_h=[0.0] * lag + [720.0] * (n - lag),
        electrolyte_mg_h=[0.0] * lag + [1000.0] * (n - lag),
        weight_kg=70,
        weight_lb=154,
        height_cm=178,
        height_ft="5' 10\"",
    )


def guide_date_workout() -> Truth:
    """A short session dated the way Nix's own guide writes it ("May 27, 2025, 12:42 PM")."""
    n, lag = 30, 15
    return Truth(
        start=f"May 27, 2025, 12:42{NNBSP}PM",
        end=f"May 27, 2025, 1:12{NNBSP}PM",
        duration="00:30:00",
        minutes=n,
        workout_type="Cycling",
        nix_index=68,
        respiration_ml_h=[25.0] * n,
        sweat_ml_h=[25.0] * lag + [600.0] * (n - lag),
        sodium_mg_h=[0.0] * lag + [500.0] * (n - lag),
        electrolyte_mg_h=[0.0] * lag + [700.0] * (n - lag),
        weight_kg=70,
        weight_lb=154,
        height_cm=178,
        height_ft="5' 10\"",
    )


# ---------------------------------------------------------------- turning a workout into Nix's two sheets


def _fmt(x: float, places: int) -> str:
    return f"{x:.{places}f}"


def summary_rows(t: Truth, units: str) -> list[tuple[str, Cell]]:
    """The Workout Summary sheet, label by label, written the way Nix writes each unit setting."""
    metric = units == "metric"
    fluid = t.total_fluid_ml()
    hours = t.minutes / 60
    sodium = t.total_mg(t.sodium_mg_h)
    electrolytes = t.total_mg(t.electrolyte_mg_h)
    composition_mg_ml = sodium / fluid if fluid else 0.0
    return [
        ("Athlete Name", FAKE_ATHLETE),
        ("Workout Name", "Afternoon Workout"),
        ("Height (cm)", str(t.height_cm)) if metric else ("Height (ft)", t.height_ft),
        ("Weight (kg)", str(t.weight_kg)) if metric else ("Weight (lb)", str(t.weight_lb)),
        ("Start Time", t.start),
        ("End Time", t.end),
        ("Duration", t.duration),
        ("Nix Index", t.nix_index),
        ("Workout Type", t.workout_type),
        ("Total Fluid Loss (ml)", _fmt(fluid, 0)) if metric else ("Total Fluid Loss (oz)", _fmt(fluid / OZ_TO_ML, 1)),
        ("Sweat Rate (ml/hr)", _fmt(fluid / hours, 0))
        if metric
        else ("Sweat Rate (oz/hr)", _fmt(fluid / hours / OZ_TO_ML, 1)),
        ("Total Electrolyte Loss (mg)", _fmt(electrolytes, 0)),
        ("Electrolyte Loss Rate (mg/hr)", _fmt(electrolytes / hours, 0)),
        ("Total Sodium Loss (mg)", _fmt(sodium, 0)),
        ("Sodium Loss Rate (mg/hr)", _fmt(sodium / hours, 0)),
        ("Sweat Composition (mg/ml)", _fmt(composition_mg_ml, 1))
        if metric
        else ("Sweat Composition (mg/oz)", _fmt(composition_mg_ml * OZ_TO_ML, 0)),
        ("Activity Type", t.workout_type),
        ("Training Pace", "--"),
    ]


def timeseries_rows(t: Truth, units: str) -> tuple[list[str], list[list[Cell]]]:
    metric = units == "metric"
    vol, rate = ("ml", "ml/hr") if metric else ("oz", "oz/hr")
    header = [
        "Minutes",
        f"Sweat Rate ({rate})",
        f"Respiration Loss Rate ({rate})",
        f"Total Fluid Loss ({vol})",
        "Electrolyte Loss Rate (mg/hr)",
        "Total Electrolyte Loss (mg)",
        "Sodium Loss Rate (mg/hr)",
        "Total Sodium Loss (mg)",
    ]

    def volume(ml: float) -> str:
        return _fmt(ml, 1) if metric else _fmt(ml / OZ_TO_ML, 1)

    rows: list[list[Cell]] = []
    for i in range(t.minutes):
        rows.append(
            [
                i + 1,
                volume(t.sweat_ml_h[i]),
                volume(t.respiration_ml_h[i]),
                volume(t.total_fluid_ml(i + 1)),
                _fmt(t.electrolyte_mg_h[i], 0),
                _fmt(t.total_mg(t.electrolyte_mg_h, i + 1), 0),
                _fmt(t.sodium_mg_h[i], 0),
                _fmt(t.total_mg(t.sodium_mg_h, i + 1), 0),
            ]
        )
    return header, rows


# ---------------------------------------------------------------- writing the .xlsx by hand

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
# Same date on every entry, so rebuilding gives byte-for-byte the same files.
FIXED_DATE = (2026, 1, 1, 0, 0, 0)
BLANK_ROWS_AFTER = 40  # the real files have hundreds of empty formatted rows after the data


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class _Strings:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.index: dict[str, int] = {}

    def add(self, s: str) -> int:
        if s not in self.index:
            self.index[s] = len(self.items)
            self.items.append(s)
        return self.index[s]


def _sheet_xml(rows: list[list[Cell]], strings: _Strings, empty_col_a: bool) -> str:
    """Rows start at row 2, column B. Timeseries rows also carry an empty text cell in column A, like Nix."""
    out = []
    for i, row in enumerate(rows):
        r = i + 2
        cells = [f'<c r="A{r}" t="s"><v>{strings.add("")}</v></c>'] if empty_col_a and i > 0 else []
        for j, v in enumerate(row):
            ref = f"{_col_letter(j + 2)}{r}"
            if isinstance(v, str):
                cells.append(f'<c r="{ref}" t="s"><v>{strings.add(v)}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
        out.append(f'<row r="{r}">{"".join(cells)}</row>')
    last = len(rows) + 1
    for r in range(last + 1, last + 1 + BLANK_ROWS_AFTER):
        out.append(f'<row r="{r}"><c r="B{r}" s="1"/></row>')
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    return f'{head}<worksheet xmlns="{MAIN}"><sheetData>{"".join(out)}</sheetData></worksheet>'


def build_xlsx(sheets: list[tuple[str, list[list[Cell]], bool]]) -> bytes:
    """sheets: (name, rows, empty column A cells) in order. Returns the .xlsx bytes."""
    strings = _Strings()
    sheet_xml = [_sheet_xml(rows, strings, empty_a) for _name, rows, empty_a in sheets]
    shared = "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in strings.items)
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    files = {
        "[Content_Types].xml": head
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + '<Default Extension="xml" ContentType="application/xml"/>'
        + '<Override PartName="/xl/workbook.xml" '
        + 'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(len(sheets))
        )
        + '<Override PartName="/xl/sharedStrings.xml" '
        + 'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        + '<Override PartName="/xl/styles.xml" '
        + 'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + "</Types>",
        "_rels/.rels": head
        + f'<Relationships xmlns="{PKG_REL}">'
        + f'<Relationship Id="rId1" Type="{DOC_REL}/officeDocument" Target="xl/workbook.xml"/>'
        + "</Relationships>",
        "xl/workbook.xml": head
        + f'<workbook xmlns="{MAIN}" xmlns:r="{DOC_REL}"><sheets>'
        + "".join(
            f'<sheet name="{escape(name)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
            for i, (name, _rows, _a) in enumerate(sheets)
        )
        + "</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": head
        + f'<Relationships xmlns="{PKG_REL}">'
        + "".join(
            f'<Relationship Id="rId{i + 1}" Type="{DOC_REL}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(len(sheets))
        )
        + f'<Relationship Id="rId{len(sheets) + 1}" Type="{DOC_REL}/sharedStrings" Target="sharedStrings.xml"/>'
        + f'<Relationship Id="rId{len(sheets) + 2}" Type="{DOC_REL}/styles" Target="styles.xml"/>'
        + "</Relationships>",
        "xl/sharedStrings.xml": head
        + f'<sst xmlns="{MAIN}" count="{len(strings.items)}" uniqueCount="{len(strings.items)}">{shared}</sst>',
        "xl/styles.xml": head
        + f'<styleSheet xmlns="{MAIN}"><fonts count="1"><font><sz val="11"/></font></fonts>'
        + '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        + '<borders count="1"><border/></borders>'
        + '<cellXfs count="2"><xf fontId="0" fillId="0" borderId="0"/>'
        + '<xf fontId="0" fillId="0" borderId="0"/></cellXfs>'
        + "</styleSheet>",
    }
    for i, xml in enumerate(sheet_xml):
        files[f"xl/worksheets/sheet{i + 1}.xml"] = xml
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            info = zipfile.ZipInfo(name, FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


def nix_export(
    t: Truth,
    units: str,
    *,
    drop_summary: tuple[str, ...] = (),
    rename_summary: dict[str, str] | None = None,
    timeseries: bool = True,
) -> bytes:
    """One fake export. The keyword options break it on purpose for the error tests."""
    rename_summary = rename_summary or {}
    summary: list[list[Cell]] = [["Data", "Value"]]
    for label, value in summary_rows(t, units):
        if label.split(" (")[0] in drop_summary:
            continue
        summary.append([rename_summary.get(label, label), value])
    sheets: list[tuple[str, list[list[Cell]], bool]] = [("Workout Summary", summary, False)]
    if timeseries:
        header, rows = timeseries_rows(t, units)
        sheets.append(("Timeseries Data", [list(header), *rows], True))
    return build_xlsx(sheets)


# A PDF renamed to .xlsx, the most likely wrong file (Nix can also share a workout as PDF).
FAKE_PDF = b"%PDF-1.4\n% fake test file, not a real PDF\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"


def all_samples() -> dict[str, bytes]:
    a, b, c = no_sweat_workout(), sweat_workout(), guide_date_workout()
    return {
        "nix_customary_no_sweat.xlsx": nix_export(a, "customary"),
        "nix_metric_no_sweat.xlsx": nix_export(a, "metric"),
        "nix_metric_sweat.xlsx": nix_export(b, "metric"),
        "nix_guide_date.xlsx": nix_export(c, "metric"),
        "broken_missing_sheet.xlsx": nix_export(a, "metric", timeseries=False),
        "broken_missing_start.xlsx": nix_export(a, "metric", drop_summary=("Start Time",)),
        "broken_unknown_unit.xlsx": nix_export(
            a, "metric", rename_summary={"Total Fluid Loss (ml)": "Total Fluid Loss (gal)"}
        ),
        "broken_pdf_renamed.xlsx": FAKE_PDF,
    }


def sample_path(name: str) -> Path:
    return SAMPLE_DIR / name


def write_samples() -> list[Path]:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, data in all_samples().items():
        p = SAMPLE_DIR / name
        p.write_bytes(data)
        paths.append(p)
    return paths


if __name__ == "__main__":
    for p in write_samples():
        print(p)
