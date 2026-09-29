"""Post-download XLSX city filter."""

import logging
from pathlib import Path

import openpyxl

log = logging.getLogger("mojo_downloader")

COUNTY_COLUMN = "County"


def filter_by_county(path: Path, counties: set[str], label: str) -> bool:
    """Remove rows from the XLSX at *path* whose county is not in *counties*.

    Overwrites the file in place. Logs kept/total counts on one line.
    Logs a warning (not an error) if the county column is absent.
    No-op if *counties* is empty.

    Returns True if filtering ran (or was skipped because counties is empty).
    Returns False if the county column was not found — caller should notify.
    """
    if not counties:
        return True

    wb = openpyxl.load_workbook(path)
    ws = wb.active

    # Locate the county column by header name (case-insensitive).
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    try:
        county_col = next(
            i for i, h in enumerate(headers)
            if h and h.strip().lower() == COUNTY_COLUMN.lower()
        )
    except StopIteration:
        log.warning("%s: '%s' column not found — county filter skipped", label, COUNTY_COLUMN)
        return False

    counties_lower = {c.strip().lower() for c in counties}
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    kept_rows = [
        row for row in rows
        if row[county_col] is not None
        and str(row[county_col]).strip().lower() in counties_lower
    ]

    # Clear all data rows in one call and re-append the kept ones.
    # Deleting rows individually is O(n²) in openpyxl and stalls on large exports.
    if rows:
        ws.delete_rows(2, len(rows))
    for row in kept_rows:
        ws.append(row)

    total = len(rows)
    kept = len(kept_rows)
    log.info(
        "%s: kept %d/%d rows (%d removed by county filter)",
        label, kept, total, total - kept,
    )
    wb.save(path)
    return True
