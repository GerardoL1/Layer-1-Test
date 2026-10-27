"""
    cd preprocessing
    python -m pytest -q tests/test_layer3_nix.py

Layer 3 Nix import. The fake exports in sample_data/layer3/ copy the real export's layout,
and their numbers come from known totals (layer3/samples.py), so every answer here is exact.
"""

import io
import random
import re
import time
import tracemalloc
import zipfile
from datetime import datetime

import pytest

from layer3 import config as C
from layer3 import samples as S
from layer3.nix import NixFileError, read_nix

OZ = C.OZ_TO_ML


def load(name):
    return read_nix(S.sample_path(name))


def make(t, units="metric", summary_edit=None, ts_edit=None):
    """A fake export with its sheets changed by hand, for the cases the samples don't cover."""
    summary = [["Data", "Value"]] + [list(r) for r in S.summary_rows(t, units)]
    header, rows = S.timeseries_rows(t, units)
    ts = [list(header)] + [list(r) for r in rows]
    if summary_edit:
        summary_edit(summary)
    if ts_edit:
        ts_edit(ts)
    return S.build_xlsx([("Workout Summary", summary, False), ("Timeseries Data", ts, True)])


def set_value(summary, label, value):
    for row in summary:
        if row[0] == label:
            row[1] = value
            return
    raise AssertionError(label)


def error_of(data):
    with pytest.raises(NixFileError) as e:
        read_nix(data)
    return str(e.value)


# ---------------------------------------------------------------- the committed sample files


def parts(data):
    """A workbook's parts unzipped, so files compare by content whatever zlib compressed them."""
    if not data.startswith(b"PK"):
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_samples_on_disk_match_the_generator():
    # If this fails after changing samples.py on purpose, run `python -m layer3.samples` and commit the files.
    for name, data in S.all_samples().items():
        assert parts(S.sample_path(name).read_bytes()) == parts(data), name


def test_sample_check_ignores_how_the_zip_was_compressed():
    # CI's zlib packs the same content into different bytes, which broke a byte-for-byte check.
    original = S.sample_path("nix_metric_sweat.xlsx").read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as src, zipfile.ZipFile(buf, "w") as out:
        for info in src.infolist():
            out.writestr(info.filename, src.read(info), compress_type=zipfile.ZIP_DEFLATED, compresslevel=1)
    assert buf.getvalue() != original
    assert parts(buf.getvalue()) == parts(original)


def test_sweat_session_reads_every_field():
    s = load("nix_metric_sweat.xlsx")
    assert s.start_local == datetime(2026, 10, 20, 18, 0)
    assert s.end_local == datetime(2026, 10, 20, 19, 0)
    assert s.duration_min == 60
    assert s.unit_system == "metric"
    assert s.fluid_loss_ml == 682  # 15 min at 30 ml/h + 45 min at 900 ml/h = 682.5, Nix writes whole ml
    assert s.sweat_rate_l_h == pytest.approx(0.682)
    assert s.sodium_mg == 540  # 45 min at 720 mg/h
    assert s.sodium_rate_mg_h == 540
    assert s.electrolytes_mg == 750
    assert s.electrolyte_rate_mg_h == 750
    assert s.sweat_composition_mg_l == pytest.approx(800)  # 0.8 mg/ml
    assert s.nix_index == 74
    assert s.workout_type == "Running"
    assert s.sweat_detected is True
    assert s.warnings == []


def test_sweat_session_minutes():
    s = load("nix_metric_sweat.xlsx")
    assert [m.minute for m in s.minutes] == list(range(1, 61))
    first, sixteenth, last = s.minutes[0], s.minutes[15], s.minutes[-1]
    assert first.sweat_rate_l_h == pytest.approx(0.03)
    assert first.respiration_rate_l_h == pytest.approx(0.03)
    assert first.sodium_rate_mg_h == 0  # a real 0 while sweat is detected, kept as 0
    assert sixteenth.sweat_rate_l_h == pytest.approx(0.9)
    assert sixteenth.sodium_rate_mg_h == 720
    assert last.total_fluid_ml == pytest.approx(682.5)
    assert last.total_sodium_mg == 540


def test_no_sweat_stores_missing_not_zero():
    s = load("nix_metric_no_sweat.xlsx")
    assert s.sweat_detected is False
    assert s.fluid_loss_ml == 62  # breathing loss only, kept as Nix recorded it
    assert s.sweat_rate_l_h == pytest.approx(0.028)
    for value in (
        s.sodium_mg,
        s.sodium_rate_mg_h,
        s.electrolytes_mg,
        s.electrolyte_rate_mg_h,
        s.sweat_composition_mg_l,
    ):
        assert value is None
    for m in s.minutes:
        assert m.total_sodium_mg is None and m.sodium_rate_mg_h is None
        assert m.total_electrolytes_mg is None and m.electrolyte_rate_mg_h is None
    assert s.warnings == [C.WARN_NO_SWEAT]


def test_salt_alone_counts_as_sweat():
    # Sweat rate never rises above breathing, but sodium was lost, so Nix did read sweat.
    def flat(ts):
        for row in ts[1:]:
            row[1] = row[2]

    s = read_nix(make(S.sweat_workout(), ts_edit=flat))
    assert s.sweat_detected is True
    assert s.sodium_mg == 540


def test_guide_date_style():
    s = load("nix_guide_date.xlsx")
    assert s.start_local == datetime(2025, 5, 27, 12, 42)
    assert s.end_local == datetime(2025, 5, 27, 13, 12)
    assert s.sweat_detected is True
    assert s.sodium_mg == 125


# ---------------------------------------------------------------- units


def test_customary_and_metric_store_the_same_values():
    c = load("nix_customary_no_sweat.xlsx")
    m = load("nix_metric_no_sweat.xlsx")
    assert c.unit_system == "customary" and m.unit_system == "metric"
    assert c.start_local == m.start_local and c.end_local == m.end_local
    # Customary rounds to 0.1 oz, about 3 ml.
    assert c.fluid_loss_ml == pytest.approx(2.1 * OZ)
    assert abs(c.fluid_loss_ml - m.fluid_loss_ml) <= 0.05 * OZ
    assert abs(c.sweat_rate_l_h - m.sweat_rate_l_h) <= 0.05 * OZ / 1000
    assert len(c.minutes) == len(m.minutes) == 133
    for a, b in zip(c.minutes, m.minutes):
        assert abs(a.total_fluid_ml - b.total_fluid_ml) <= 0.05 * OZ + 0.05


def test_customary_sweat_converts_every_unit():
    s = read_nix(make(S.sweat_workout(), "customary"))
    assert s.unit_system == "customary"
    assert s.fluid_loss_ml == pytest.approx(23.1 * OZ)  # 682.5 ml written as 23.1 oz
    assert s.sweat_rate_l_h == pytest.approx(23.1 * OZ / 1000)
    assert s.sweat_composition_mg_l == pytest.approx(23 * 1000 / OZ)  # 0.79 mg/ml written as 23 mg/oz
    assert s.sodium_mg == 540  # mg is the same in both settings
    assert s.minutes[20].sweat_rate_l_h == pytest.approx(30.4 * OZ / 1000)  # 900 ml/h is 30.4 oz/hr


def test_units_match_in_any_case_and_spacing():
    def shout(summary):
        for row in summary:
            if row[0] == "Total Fluid Loss (ml)":
                row[0] = "  total FLUID loss ( ML ) "

    s = read_nix(make(S.sweat_workout(), summary_edit=shout))
    assert s.fluid_loss_ml == 682


def test_weight_from_the_file_is_only_a_suggestion_in_kg():
    assert load("nix_customary_no_sweat.xlsx").file_weight_kg == pytest.approx(73.5)  # 162 lb
    assert load("nix_metric_no_sweat.xlsx").file_weight_kg == 73


def test_odd_weight_means_no_suggestion_not_an_error():
    def stone(summary):
        for row in summary:
            if row[0] == "Weight (kg)":
                row[0] = "Weight (st)"

    def huge(summary):
        set_value(summary, "Weight (kg)", "900")

    assert read_nix(make(S.sweat_workout(), summary_edit=stone)).file_weight_kg is None
    assert read_nix(make(S.sweat_workout(), summary_edit=huge)).file_weight_kg is None


# ---------------------------------------------------------------- numbers and dates


def test_numbers_as_text_and_dashes():
    def edit(summary):
        set_value(summary, "Sweat Rate (ml/hr)", "--")
        set_value(summary, "Nix Index", "74")  # text instead of a real number
        set_value(summary, "Total Sodium Loss (mg)", " 1,150 ")

    s = read_nix(make(S.sweat_workout(), summary_edit=edit))
    assert s.sweat_rate_l_h is None
    assert s.nix_index == 74
    assert s.sodium_mg == 1150


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Oct 25, 2026 at 2:55 PM", datetime(2026, 10, 25, 14, 55)),
        ("May 27, 2025, 12:42 PM", datetime(2025, 5, 27, 12, 42)),
        ("May 27, 2025, 12:05 AM", datetime(2025, 5, 27, 0, 5)),
        ("September 3, 2026 at 9:07 am", datetime(2026, 9, 3, 9, 7)),
        ("Oct 25, 2026 at 14:55", datetime(2026, 10, 25, 14, 55)),
        ("Oct  25 2026, 2:55:30 PM", datetime(2026, 10, 25, 14, 55, 30)),
        ("46320.5", datetime(2026, 10, 25, 12, 0)),  # an Excel date cell
    ],
)
def test_date_formats(text, expected):
    def edit(summary):
        set_value(summary, "Start Time", text)
        set_value(summary, "End Time", "Dec 31, 2026 at 11:59 PM")

    assert read_nix(make(S.sweat_workout(), summary_edit=edit)).start_local == expected


@pytest.mark.parametrize("text", ["25/10/2026 14:55", "Foo 25, 2026 at 2:55 PM", "Oct 25, 2026 at 13:55 PM", "soon"])
def test_unreadable_dates(text):
    data = make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "Start Time", text))
    assert error_of(data) == C.ERR_BAD_DATE.format(label="start time", value=text)


# ---------------------------------------------------------------- warnings (the import still goes ahead)


def test_fluid_that_doesnt_match_the_rate_is_a_warning():
    s = read_nix(make(S.sweat_workout(), summary_edit=lambda x: set_value(x, "Total Fluid Loss (ml)", "1200")))
    assert s.fluid_loss_ml == 1200
    assert s.warnings == [C.WARN_FLUID_MISMATCH.format(fluid=1200, expected=682)]


def test_small_rounding_is_not_a_warning():
    # 62 ml against 28 ml/h is fine, and so is the Customary file's 2.1 oz against 0.9 oz/hr.
    assert load("nix_metric_no_sweat.xlsx").warnings == [C.WARN_NO_SWEAT]
    assert load("nix_customary_no_sweat.xlsx").warnings == [C.WARN_NO_SWEAT]


def test_short_timeseries_is_a_warning():
    def cut(ts):
        del ts[41:]  # header + 40 minutes of a 60-minute workout

    s = read_nix(make(S.sweat_workout(), ts_edit=cut))
    assert len(s.minutes) == 40
    assert s.warnings == [C.WARN_MINUTES_MISMATCH.format(rows=40, minutes=60)]


def test_duration_that_doesnt_match_the_times_is_a_warning():
    s = read_nix(make(S.sweat_workout(), summary_edit=lambda x: set_value(x, "Duration", "00:30:00")))
    assert C.WARN_DURATION_MISMATCH.format(duration=30, span=60) in s.warnings


def test_missing_duration_uses_start_and_end():
    s = read_nix(make(S.sweat_workout(), summary_edit=lambda x: set_value(x, "Duration", "--")))
    assert s.duration_min == 60
    assert s.warnings == []


# ---------------------------------------------------------------- personal details


def test_athlete_name_is_never_read():
    for name in ("nix_customary_no_sweat.xlsx", "nix_metric_sweat.xlsx"):
        s = load(name)
        assert S.FAKE_ATHLETE not in repr(s)
        assert "Afternoon Workout" not in repr(s)  # the workout name isn't kept either


def test_layout_found_by_labels_not_position():
    # Rows shuffled and the table moved: the reader still finds everything by its label.
    def shuffle(summary):
        summary[1:] = list(reversed(summary[1:]))

    s = read_nix(make(S.sweat_workout(), summary_edit=shuffle))
    assert s.fluid_loss_ml == 682 and s.sodium_mg == 540


def test_reading_stops_at_the_first_empty_minute():
    def gap(ts):
        ts[31][0] = "--"  # minute 31 has no number, so the data ends at 30

    assert len(read_nix(make(S.sweat_workout(), ts_edit=gap)).minutes) == 30


# ---------------------------------------------------------------- errors, one message each


def test_pdf_renamed():
    assert error_of(S.sample_path("broken_pdf_renamed.xlsx").read_bytes()) == C.ERR_PDF


def test_not_an_excel_file():
    assert error_of(b"Minutes,Sweat Rate\n1,0.9\n") == C.ERR_NOT_XLSX


def test_a_zip_that_isnt_a_workbook():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("export.xml", "<HealthData/>")
    assert error_of(buf.getvalue()) == C.ERR_NOT_XLSX


def test_damaged_file():
    data = S.sample_path("nix_metric_sweat.xlsx").read_bytes()
    assert error_of(data[:400]) == C.ERR_DAMAGED


def test_xml_with_a_doctype_is_refused():
    data = make(S.sweat_workout())
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w") as out:
        for info in src.infolist():
            raw = src.read(info)
            if info.filename == "xl/sharedStrings.xml":
                raw = raw.replace(b"<sst", b'<!DOCTYPE sst [<!ENTITY a "x">]><sst', 1)
            out.writestr(info, raw)
    assert error_of(buf.getvalue()) == C.ERR_DAMAGED


def test_far_too_big_when_unpacked():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", b"<workbook/>")
        z.writestr("xl/worksheets/sheet1.xml", b"\0" * (C.MAX_UNZIPPED_BYTES + 1))
    assert len(buf.getvalue()) < 100_000  # tiny on the wire
    assert error_of(buf.getvalue()) == C.ERR_TOO_BIG


def test_missing_sheet():
    data = S.sample_path("broken_missing_sheet.xlsx").read_bytes()
    assert error_of(data) == C.ERR_MISSING_SHEET.format(sheet="Timeseries Data")


def test_missing_header():
    def rename(summary):
        summary[0][0] = "Field"

    data = make(S.sweat_workout(), summary_edit=rename)
    assert error_of(data) == C.ERR_MISSING_HEADER.format(sheet="Workout Summary", header="Data")


@pytest.mark.parametrize("label", ["Start Time", "End Time", "Total Fluid Loss"])
def test_missing_required_rows(label):
    t = S.sweat_workout()
    data = S.nix_export(t, "metric", drop_summary=(label,))
    assert error_of(data) == C.ERR_MISSING_ROW.format(label=label)


def test_required_row_with_no_value():
    data = make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "End Time", "--"))
    assert error_of(data) == C.ERR_MISSING_ROW.format(label="End Time")


def test_unknown_unit_names_the_label():
    data = S.sample_path("broken_unknown_unit.xlsx").read_bytes()
    assert error_of(data) == C.ERR_UNKNOWN_UNIT.format(label="Total Fluid Loss (gal)")


def test_unknown_unit_in_the_timeseries():
    def litres(ts):
        ts[0][1] = "Sweat Rate (L/hr)"

    assert error_of(make(S.sweat_workout(), ts_edit=litres)) == C.ERR_UNKNOWN_UNIT.format(label="Sweat Rate (L/hr)")


def test_missing_timeseries_column():
    def drop(ts):
        for row in ts:
            del row[2]  # Respiration Loss Rate

    expected = C.ERR_MISSING_COLUMN.format(sheet="Timeseries Data", label="Respiration Loss Rate")
    assert error_of(make(S.sweat_workout(), ts_edit=drop)) == expected


@pytest.mark.parametrize("value", ["abc", "nan", "inf", "1.2.3"])
def test_bad_numbers(value):
    data = make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "Total Sodium Loss (mg)", value))
    assert error_of(data) == C.ERR_BAD_NUMBER.format(label="Total Sodium Loss (mg)", value=value)


def test_negative_numbers():
    data = make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "Total Fluid Loss (ml)", "-5"))
    assert error_of(data) == C.ERR_NEGATIVE.format(label="Total Fluid Loss (ml)", value="-5")


def test_fractional_minute():
    def half(ts):
        ts[5][0] = 4.5

    assert error_of(make(S.sweat_workout(), ts_edit=half)) == C.ERR_BAD_NUMBER.format(label="Minutes", value="4.5")


def test_end_a_little_before_start_is_left_to_the_time_zone():
    # When clocks go back, 1:50 AM (summer time) to 1:10 AM (winter time) is a real 20-minute workout.
    # The file has no time zone, so the reader keeps it and the server checks the real times.
    def edit(summary):
        set_value(summary, "Start Time", "Nov 2, 2025 at 1:50 AM")
        set_value(summary, "End Time", "Nov 2, 2025 at 1:10 AM")
        set_value(summary, "Duration", "00:20:00")

    s = read_nix(make(S.sweat_workout(), summary_edit=edit))
    assert s.end_local < s.start_local
    assert s.file_duration_min == 20


def test_end_before_start():
    data = make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "End Time", "Oct 20, 2026 at 5:00 PM"))
    assert error_of(data) == C.ERR_END_BEFORE_START


# ---------------------------------------------------------------- findings from the first testing pass


def patch(data, name, fn):
    """Rebuild a workbook with one part changed, to make files Nix itself would never write."""
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            raw = src.read(info)
            out.writestr(info, fn(raw) if info.filename == name else raw)
    return buf.getvalue()


SHEET1 = "xl/worksheets/sheet1.xml"


def sweat_file():
    return S.sample_path("nix_metric_sweat.xlsx").read_bytes()


def test_corrupted_bytes_never_crash():
    # 1. Flipping a few bytes used to escape as zlib.error, which the server would turn into a 500.
    data = sweat_file()
    rng = random.Random(7)
    for _ in range(400):
        broken = bytearray(data)
        for _ in range(rng.randint(1, 6)):
            broken[rng.randrange(len(broken))] ^= rng.randint(1, 255)
        try:
            read_nix(bytes(broken))
        except NixFileError:
            pass


def _lying_zip(hidden_bytes):
    """A zip whose listing says sharedStrings.xml is 100 bytes, while its data unpacks to far more."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", b"<workbook/>")
        z.writestr("xl/_rels/workbook.xml.rels", b"<Relationships/>")
        z.writestr("xl/sharedStrings.xml", b" " * hidden_bytes)
    data = bytearray(buf.getvalue())
    small = (100).to_bytes(4, "little")
    for m in re.finditer(rb"PK\x03\x04", data):  # local headers: uncompressed size at +22
        if data[m.start() + 30 : m.start() + 50].startswith(b"xl/sharedStrings.xml"):
            data[m.start() + 22 : m.start() + 26] = small
    for m in re.finditer(rb"PK\x01\x02", data):  # central directory: uncompressed size at +24
        if data[m.start() + 46 : m.start() + 66].startswith(b"xl/sharedStrings.xml"):
            data[m.start() + 24 : m.start() + 28] = small
    return bytes(data)


def test_zip_that_lies_about_its_size_is_refused_without_using_much_memory():
    # 2. The size check trusted the listing, and reading a part unpacked all of it at once.
    data = _lying_zip(60 * 1024 * 1024)
    assert len(data) < 200_000
    tracemalloc.start()
    try:
        with pytest.raises(NixFileError):
            read_nix(data)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 30 * 1024 * 1024


def test_huge_row_number_is_quick():
    # 3. The summary was walked row by row up to the biggest row number in the sheet.
    def far_row(raw):
        return raw.replace(
            b"</sheetData>", b'<row r="200000000"><c r="B200000000" t="s"><v>0</v></c></row></sheetData>'
        )

    started = time.perf_counter()
    s = read_nix(patch(sweat_file(), SHEET1, far_row))
    assert time.perf_counter() - started < 2
    assert s.fluid_loss_ml == 682


def _new_zip_version(data):
    # Central directory "version needed to extract" set to 7.6, which Python can't open.
    out = bytearray(data)
    for m in re.finditer(rb"PK\x01\x02", out):
        out[m.start() + 6] = 76
    return bytes(out)


@pytest.mark.parametrize(
    "make_bad",
    [
        _new_zip_version,
        lambda d: patch(d, SHEET1, lambda r: r.replace(b'encoding="UTF-8"', b'encoding="foo-bar"')),
        lambda d: patch(d, SHEET1, lambda r: r.replace(b'<row r="3">', b'<row r="3x">', 1)),
        lambda d: patch(d, SHEET1, lambda r: r.replace(b'<c r="C2" t="s"><v>1</v>', b'<c r="C2" t="s"><v>1.2</v>', 1)),
    ],
    ids=["zip version", "unknown encoding", "row number with letters", "shared string index not whole"],
)
def test_odd_workbooks_give_a_plain_error(make_bad):
    # 4. These escaped as NotImplementedError, LookupError or a raw ValueError.
    assert error_of(make_bad(sweat_file())) == C.ERR_DAMAGED


def test_odd_digits_in_duration_dont_crash():
    # 4. "²" passed isdigit() and then broke int().
    s = read_nix(make(S.sweat_workout(), summary_edit=lambda x: set_value(x, "Duration", "0²:00:00")))
    assert s.duration_min == 60
    assert s.warnings == [C.WARN_DURATION_UNREADABLE.format(value="0²:00:00")]


@pytest.mark.parametrize("wrap", [bytearray, memoryview])
def test_bytes_like_input(wrap):
    # 4. Only bytes were accepted, anything else was taken for a path.
    assert read_nix(wrap(sweat_file())).fluid_loss_ml == 682


def test_values_that_overflow_after_conversion_are_refused():
    # 5. 1e308 oz passed the infinity check, then became inf ml.
    data = make(
        S.no_sweat_workout(), "customary", summary_edit=lambda s: set_value(s, "Total Fluid Loss (oz)", "1e308")
    )
    assert error_of(data) == C.ERR_BAD_NUMBER.format(label="Total Fluid Loss (oz)", value="1e308")


def test_far_too_high_values_are_refused():
    # 5. No value had any upper limit.
    data = make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "Total Fluid Loss (ml)", "99999999"))
    assert error_of(data) == C.ERR_IMPLAUSIBLE.format(label="Total Fluid Loss (ml)", value="99999999")


def test_far_too_high_minute_values_are_refused():
    def spike(ts):
        ts[20][1] = "99999999"

    assert error_of(make(S.sweat_workout(), ts_edit=spike)) == C.ERR_IMPLAUSIBLE.format(
        label="Sweat Rate (ml/hr)", value="99999999"
    )


def test_utf16_xml_with_a_doctype_is_refused():
    # 6. The DOCTYPE check only looked for ASCII bytes, so UTF-16 slipped past it.
    def utf16(raw):
        text = raw.decode("utf-8").replace('encoding="UTF-8"', 'encoding="UTF-16"')
        text = text.replace("<sst", '<!DOCTYPE sst [<!ENTITY f "Running-from-entity">]><sst', 1)
        return text.encode("utf-16")

    assert error_of(patch(sweat_file(), "xl/sharedStrings.xml", utf16)) == C.ERR_DAMAGED


def test_missing_breathing_values_dont_hide_real_sweat():
    # 7. A minute only counted as sweat when both rates were there.
    def no_breathing(ts):
        for row in ts[1:]:
            row[2] = "--"

    def no_salt(summary):
        set_value(summary, "Total Sodium Loss (mg)", "0")
        set_value(summary, "Total Electrolyte Loss (mg)", "0")

    s = read_nix(make(S.sweat_workout(), summary_edit=no_salt, ts_edit=no_breathing))
    assert s.sweat_detected is True


def test_long_bad_values_are_cut_short_in_messages():
    # 8. The whole value went into the message, even 4 MB of it.
    junk = "x" * 900  # under MAX_CELL_CHARS, which refuses longer cells before they're read
    msg = error_of(make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "Total Fluid Loss (ml)", junk)))
    assert len(msg) < 200
    assert msg.startswith("We couldn't read the number for 'Total Fluid Loss (ml)'")


def test_one_rounded_customary_minute_isnt_sweat():
    # 9. 28 vs 29 ml/h rounds to 0.9 vs 1.0 oz/hr, which crossed the old 0.0005 L/h cut-off.
    def bump(ts):
        ts[10][1] = "1.0"

    s = read_nix(make(S.no_sweat_workout(), "customary", ts_edit=bump))
    assert s.sweat_detected is False
    assert s.sodium_mg is None


@pytest.mark.parametrize("value", ["1", "0.5", "Jan 1, 1999 at 9:00 AM"])
def test_dates_before_2000_are_refused(value):
    # 10. An Excel day count of 1 meant a date in 1899.
    def edit(summary):
        set_value(summary, "Start Time", value)
        set_value(summary, "End Time", "Oct 20, 2026 at 7:00 PM")

    assert error_of(make(S.sweat_workout(), summary_edit=edit)) == C.ERR_BAD_DATE.format(
        label="start time", value=value
    )


@pytest.mark.parametrize("value", ["1_000", "٤٢", "５００", "+682", "1e3"])
def test_only_plain_numbers(value):
    # 11. Python's float() reads all of these, Nix never writes them.
    data = make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "Total Fluid Loss (ml)", value))
    assert error_of(data) == C.ERR_BAD_NUMBER.format(label="Total Fluid Loss (ml)", value=value)


def test_minus_zero_is_negative():
    data = make(S.sweat_workout(), summary_edit=lambda s: set_value(s, "Total Fluid Loss (ml)", "-0"))
    assert error_of(data) == C.ERR_NEGATIVE.format(label="Total Fluid Loss (ml)", value="-0")


@pytest.mark.parametrize("value", ["1:00", "01:00:00.5", "1 h"])
def test_durations_other_than_hh_mm_ss_use_the_times(value):
    # 12. "1:00" was read as one minute, the others were dropped without a word.
    s = read_nix(make(S.sweat_workout(), summary_edit=lambda x: set_value(x, "Duration", value)))
    assert s.duration_min == 60
    assert s.warnings == [C.WARN_DURATION_UNREADABLE.format(value=value)]


@pytest.mark.parametrize("label", ["Total Fluid Loss ml", "Total Fluid Loss [ml]", "Total Fluid Loss ((ml))"])
def test_unit_outside_brackets_names_the_label(label):
    # 13. These said the row was missing, which sends people looking for the wrong problem.
    def rename(summary):
        for row in summary:
            if row[0] == "Total Fluid Loss (ml)":
                row[0] = label

    assert error_of(make(S.sweat_workout(), summary_edit=rename)) == C.ERR_UNKNOWN_UNIT.format(label=label)


def test_minutes_heading_with_a_unit():
    def heading(ts):
        ts[0][0] = "Minutes (min)"

    assert len(read_nix(make(S.sweat_workout(), ts_edit=heading)).minutes) == 60


def test_password_protected_file():
    # 13. Protected Excel files aren't zips, so they were called "not an Excel file".
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 500
    assert error_of(ole) == C.ERR_PROTECTED


@pytest.mark.parametrize("value", ["High", "-3"])
def test_odd_nix_index_is_left_out(value):
    # 13. Nix Index isn't needed, so it shouldn't refuse the whole file.
    s = read_nix(make(S.sweat_workout(), summary_edit=lambda x: set_value(x, "Nix Index", value)))
    assert s.nix_index is None
    assert s.fluid_loss_ml == 682


def test_mixed_units_count_as_the_less_precise_setting():
    # 14. unit_system only looked at the fluid unit.
    def mix(summary):
        for row in summary:
            if row[0] == "Sweat Rate (ml/hr)":
                row[0], row[1] = "Sweat Rate (oz/hr)", "23.1"

    s = read_nix(make(S.sweat_workout(), summary_edit=mix))
    assert s.unit_system == "customary"
    assert s.sweat_rate_l_h == pytest.approx(23.1 * OZ / 1000)


def test_first_sheet_with_a_name_wins():
    # 14. A later sheet with the same name replaced the real one.
    t = S.sweat_workout()
    summary = [["Data", "Value"]] + [list(r) for r in S.summary_rows(t, "metric")]
    header, rows = S.timeseries_rows(t, "metric")
    data = S.build_xlsx(
        [
            ("Workout Summary", summary, False),
            ("Timeseries Data", [list(header), *rows], True),
            ("workout summary", [["Notes"]], False),
        ]
    )
    assert read_nix(data).fluid_loss_ml == 682


def test_inline_text_drops_pronunciation_hints():
    # 14. Shared strings dropped rPh text, inline strings kept it.
    def inline(raw):
        cell = b'<c r="C11" t="inlineStr"><is><t>Running</t><rPh sb="0" eb="1"><t>X</t></rPh></is></c>'
        return re.sub(rb'<c r="C11" t="s"><v>\d+</v></c>', cell, raw)

    assert read_nix(patch(sweat_file(), SHEET1, inline)).workout_type == "Running"


def test_invisible_characters_in_dates():
    # 14. A zero-width space or BOM isn't whitespace to Python, so the date was refused.
    def edit(summary):
        set_value(summary, "Start Time", "﻿Oct 20, 2026 at​ 6:00 PM")

    assert read_nix(make(S.sweat_workout(), summary_edit=edit)).start_local == datetime(2026, 10, 20, 18, 0)


# ---------------------------------------------------------------- findings from the Layer 1 tab's review


def test_one_huge_text_cell_shared_by_many_cells_is_refused_quickly():
    # S1. A small file whose one huge shared string is used by many cells cost minutes of CPU.
    def huge(raw):
        return raw.replace(b">Value</t>", b">" + b"a" * 1_000_000 + b"</t>", 1)

    def many(raw):
        cells = b"".join(b'<row r="%d"><c r="B%d" t="s"><v>1</v></c></row>' % (r, r) for r in range(300, 400))
        return raw.replace(b"</sheetData>", cells + b"</sheetData>")

    data = patch(patch(sweat_file(), "xl/sharedStrings.xml", huge), SHEET1, many)
    started = time.perf_counter()
    assert error_of(data) == C.ERR_LONG_CELL
    assert time.perf_counter() - started < 1


@pytest.mark.parametrize("value", ["1" * 400, "9" * 20, "100000"])
def test_minutes_that_cant_be_real_are_refused(value):
    # S2. "1"*400 crashed with OverflowError, and huge whole numbers broke the save into SQLite.
    def edit(ts):
        ts[5][0] = value

    assert error_of(make(S.sweat_workout(), ts_edit=edit)) == C.ERR_BAD_NUMBER.format(
        label="Minutes", value=value[: C.ERROR_VALUE_MAX_CHARS] + ("…" if len(value) > C.ERROR_VALUE_MAX_CHARS else "")
    )


def test_infinite_nix_index_is_left_out():
    # S3. "9"*400 was stored as infinity.
    s = read_nix(make(S.sweat_workout(), summary_edit=lambda x: set_value(x, "Nix Index", "9" * 400)))
    assert s.nix_index is None
