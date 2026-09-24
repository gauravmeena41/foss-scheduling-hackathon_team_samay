"""Uploaded Excel/CSV -> clean roster the engine can read.

Real files are messy: different header spellings, dd/mm/yyyy dates, blank rows, duplicates, a cover sheet.
`read_upload` fixes what it safely can, skips rows it can't use, and says what it did.
Returns (roster DataFrame or None, blocking problems, notes).
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

from model import DISPOSED, LIFECYCLE, SIDE_TYPES, norm

REQUIRED = ["case_number", "filing_date", "purpose_of_next_hearing"]
OPTIONAL = ["advocate_id", "party_id", "current_stage", "last_hearing_summary", "total_hearings_held"]

ALIASES = {
    "case_number": ["case_number", "case_no", "case_id", "case", "case_num", "caseno", "case_ref", "cnr", "cnr_number"],
    "filing_number": ["filing_number", "filing_no"],
    "filing_date": ["filing_date", "date_of_filing", "filed_on", "filing_dt", "institution_date", "date_filed"],
    "advocate_id": ["advocate_id", "advocate", "advocate_name", "counsel", "adv_id", "lawyer"],
    "party_id": ["party_id", "party", "party_name", "complainant", "litigant_id"],
    "current_stage": ["current_stage", "stage", "case_stage"],
    "last_hearing_summary": ["last_hearing_summary", "summary", "last_order", "last_order_summary",
                             "order_summary", "last_hearing", "remarks_of_last_hearing"],
    "purpose_of_next_hearing": ["purpose_of_next_hearing", "next_purpose", "purpose", "next_hearing_purpose",
                                "purpose_of_hearing"],
    "total_hearings_held": ["total_hearings_held", "total_hearings", "hearings_held", "no_of_hearings",
                            "number_of_hearings"],
}
VALID = set(LIFECYCLE) | SIDE_TYPES
PURPOSE_ALIASES = {
    "JUDGMENT": "JUDGEMENT", "ORDERS": "JUDGEMENT", "FOR_JUDGMENT": "JUDGEMENT", "FOR_JUDGEMENT": "JUDGEMENT",
    "ARGUMENT": "ARGUMENTS", "FINAL_ARGUMENTS": "ARGUMENTS",
    "EVIDENCE": "EVIDENCE_COMPLAINANT", "COMPLAINANT_EVIDENCE": "EVIDENCE_COMPLAINANT", "CW_EVIDENCE": "EVIDENCE_COMPLAINANT",
    "DEFENCE_EVIDENCE": "EVIDENCE_ACCUSED", "DEFENSE_EVIDENCE": "EVIDENCE_ACCUSED", "ACCUSED_EVIDENCE": "EVIDENCE_ACCUSED",
    "S351": "EXAMINATION_UNDER_S351_BNSS", "S313": "EXAMINATION_UNDER_S351_BNSS",
    "EXAMINATION_UNDER_S313": "EXAMINATION_UNDER_S351_BNSS", "EXAMINATION": "EXAMINATION_UNDER_S351_BNSS",
    "SUMMONS": "APPEARANCE", "NOTICE": "APPEARANCE", "APPEAR": "APPEARANCE",
    "NBW": "WARRANT", "BW": "WARRANT", "WARRANTS": "WARRANT",
    "CONDONATION": "DELAY_CONDONATION_HEARING", "DELAY_CONDONATION": "DELAY_CONDONATION_HEARING",
    "REPORT": "REPORTS", "APPLICATION": "APPLICATION_REVIEW", "IA": "APPLICATION_REVIEW",
    "PLEA_RECORDING": "PLEA", "FRAMING_OF_NOTICE": "PLEA", "ADMISSION_HEARING": "ADMISSION",
    "DISPOSED_OF": DISPOSED, "CLOSED": DISPOSED, "DECIDED": DISPOSED,
}


def _key(col) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^0-9a-z]+", "_", str(col).strip().lower())).strip("_")


def _rename(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: _key(c) for c in df.columns})
    df = df.loc[:, ~df.columns.duplicated()]
    ren = {}
    for target, names in ALIASES.items():
        if target in df.columns:
            continue
        for n in names:
            if n in df.columns and n not in ren:
                ren[n] = target
                break
    return df.rename(columns=ren)


def _score_header(cols) -> int:
    keys = {_key(c) for c in cols}
    return sum(any(n in keys for n in ALIASES[t]) for t in REQUIRED)


def _read_frames(name: str, raw: bytes) -> list[pd.DataFrame]:
    low = name.lower()
    if low.endswith(".csv"):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                return [pd.read_csv(io.BytesIO(raw), encoding=enc, dtype=str, keep_default_na=True)]
            except UnicodeDecodeError:
                continue
    if low.endswith(".xls"):
        try:
            return list(pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None, dtype=object).values())
        except ImportError:
            raise ValueError("old .xls format — please save the file as .xlsx (Excel: File → Save As → .xlsx)")
    return list(pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None, dtype=object,
                              engine="openpyxl").values())


def _with_header(frame: pd.DataFrame) -> pd.DataFrame:
    """Excel sheets read header=None: find the header row among the first 15 rows."""
    if all(isinstance(c, str) for c in frame.columns):     # CSV already has its header
        return frame
    best, best_row = -1, 0
    for i in range(min(15, len(frame))):
        s = _score_header(frame.iloc[i].tolist())
        if s > best:
            best, best_row = s, i
    body = frame.iloc[best_row + 1:].reset_index(drop=True)
    body.columns = [str(c) if not (isinstance(c, float) and np.isnan(c)) else f"col_{j}"
                    for j, c in enumerate(frame.iloc[best_row].tolist())]
    return body


def _dates(s: pd.Series) -> pd.Series:
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    is_dt = s.map(lambda v: isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year"))
    if is_dt.any():
        out[is_dt] = pd.to_datetime(s[is_dt].astype(str), errors="coerce")
    num = pd.to_numeric(s.where(~is_dt), errors="coerce")
    serial = num.between(20000, 80000)                      # Excel serial day numbers
    if serial.any():
        out[serial] = pd.to_datetime(num[serial], unit="D", origin="1899-12-30")
    rest = out.isna() & s.notna() & ~serial
    if rest.any():
        txt = s[rest].astype(str).str.strip().str.replace(r"\s+00:00:00$", "", regex=True)
        iso = pd.to_datetime(txt, errors="coerce", format="%Y-%m-%d")
        other = pd.to_datetime(txt[iso.isna()], errors="coerce", dayfirst=True, format="mixed")
        out[rest] = iso.fillna(other)
    return out.dt.normalize()


def _purpose(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
        return ""
    p = norm(re.sub(r"[^0-9A-Za-z]+", " ", str(v)))
    return PURPOSE_ALIASES.get(p, p)


def read_upload(name: str, raw: bytes, as_of: str, hearing_cols: list[str]) -> tuple[pd.DataFrame | None, list[str], list[str]]:
    notes: list[str] = []
    try:
        frames = _read_frames(name, raw)
    except ValueError as e:
        return None, [str(e)], notes
    except Exception as e:  # noqa: BLE001
        return None, [f"Couldn't open the file as Excel/CSV ({type(e).__name__}). "
                      "Save it as .xlsx or .csv and upload again."], notes
    frames = [_with_header(f) for f in frames if f is not None and f.shape[0] > 0]
    if not frames:
        return None, ["The file is empty."], notes
    frames.sort(key=lambda f: _score_header(f.columns), reverse=True)
    df = _rename(frames[0])
    if len(frames) > 1 and _score_header(frames[0].columns) > 0:
        notes.append("Read the sheet that has the case columns (the workbook has several sheets).")

    if "purpose_of_next_hearing" not in df.columns and "current_stage" in df.columns:
        df["purpose_of_next_hearing"] = df["current_stage"]
        notes.append("No next-purpose column — used the current stage as the next purpose.")
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        return None, [f"Missing column(s): {', '.join(missing)}. Found: "
                      f"{', '.join(map(str, list(df.columns)[:12]))}{' …' if df.shape[1] > 12 else ''}. "
                      "Download the sample Excel template from the sidebar to see the expected columns."], notes

    df = df.dropna(how="all").reset_index(drop=True)
    df["case_number"] = df["case_number"].map(lambda v: "" if pd.isna(v) else
                                              (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()))
    skipped: dict[str, int] = {}

    def skip(mask: pd.Series, why: str):
        nonlocal df
        n = int(mask.sum())
        if n:
            skipped[why] = skipped.get(why, 0) + n
            df = df[~mask].reset_index(drop=True)

    skip(df["case_number"] == "", "no case number")
    df["filing_date"] = _dates(df["filing_date"])
    skip(df["filing_date"].isna(), "filing date missing or unreadable")
    skip(df["filing_date"] > pd.Timestamp(as_of), "filing date in the future")

    df["purpose_of_next_hearing"] = df["purpose_of_next_hearing"].map(_purpose)
    stage = df["current_stage"].map(_purpose) if "current_stage" in df.columns else pd.Series("", index=df.index)
    blank = df["purpose_of_next_hearing"] == ""
    df.loc[blank, "purpose_of_next_hearing"] = stage[blank]
    skip(df["purpose_of_next_hearing"] == DISPOSED, "already disposed")
    bad = ~df["purpose_of_next_hearing"].isin(VALID)
    if bad.any():
        vals = sorted({v or "(blank)" for v in df.loc[bad, "purpose_of_next_hearing"]})[:6]
        skip(bad, "next purpose not recognised (" + ", ".join(vals) + ")")
    dup = df["case_number"].duplicated(keep="first")
    skip(dup, "duplicate case number (kept the first)")

    if df.empty:
        if not skipped:
            return None, ["The file has no case rows."], notes
        why = "; ".join(f"{n} × {w}" for w, n in skipped.items())
        return None, [f"No usable cases left after checking the rows ({why})."], notes

    # optional columns: sensible defaults
    df["current_stage"] = stage.reindex(df.index) if "current_stage" in df.columns else df["purpose_of_next_hearing"]
    df["current_stage"] = df["current_stage"].where(df["current_stage"].isin(VALID), df["purpose_of_next_hearing"])
    df["current_stage"] = df["current_stage"].str.replace("_", " ").str.title()
    df["purpose_of_next_hearing"] = df["purpose_of_next_hearing"].str.replace("_", " ").str.title()
    if "advocate_id" not in df.columns:
        df["advocate_id"] = np.nan
    df["advocate_id"] = df["advocate_id"].map(lambda v: "ADV-UNKNOWN" if pd.isna(v) or str(v).strip() == "" else str(v).strip())
    if "party_id" not in df.columns:
        df["party_id"] = np.nan
    df["party_id"] = [c if pd.isna(v) or str(v).strip() == "" else str(v).strip()
                      for c, v in zip(df["case_number"], df["party_id"])]
    if "last_hearing_summary" not in df.columns:
        df["last_hearing_summary"] = ""
        notes.append("No last-hearing summary column — every case treated as 'order not read'.")
    df["last_hearing_summary"] = df["last_hearing_summary"].map(lambda v: "" if pd.isna(v) else str(v))
    for c in hearing_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).clip(lower=0).astype(int) if c in df.columns else 0
    extra_h = [c for c in df.columns if c.startswith("hearings_") and c not in hearing_cols]
    df = df.drop(columns=extra_h)
    per_type = df[hearing_cols].sum(axis=1)
    if "total_hearings_held" not in df.columns:
        df["total_hearings_held"] = np.nan
    tot = pd.to_numeric(df["total_hearings_held"], errors="coerce")
    df["total_hearings_held"] = tot.fillna(per_type).clip(lower=0).round().astype(int)
    if "filing_number" not in df.columns:
        df["filing_number"] = df["case_number"]
    df["filing_date"] = df["filing_date"].dt.strftime("%Y-%m-%d")

    if skipped:
        notes.append("Skipped " + "; ".join(f"{n} row(s): {w}" for w, n in skipped.items()) + ".")
    keep = ["case_number", "filing_number", "filing_date", "advocate_id", "party_id", "current_stage",
            "last_hearing_summary", "purpose_of_next_hearing"] + hearing_cols + ["total_hearings_held"]
    others = [c for c in df.columns if c not in keep]
    return df[keep + others], [], notes
