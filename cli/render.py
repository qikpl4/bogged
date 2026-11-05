"""Plain-text and CSV rendering of lookup results.

The plain-text table wraps cells at column boundaries (multi-line rows stay
aligned) so it survives narrow terminals. When max_width is None, cells are
never wrapped. The CSV output is never wrapped and uses empty fields for
absent values.
"""

import csv
import io
import textwrap

import binary

ABSENT = "-"
GAP = 2
HEADERS = ["Kind", *(side.capitalize() for side in binary.SIDE_ORDER), "Descriptor"]


def _entry_text(record: binary.Record, side: str) -> str | None:
    entry = record.sides.get(side)
    if entry is None or not entry.name:
        return None
    return f"{entry.owner}.{entry.name}" if entry.owner else entry.name


def _row_cells(record: binary.Record) -> list[str]:
    return [
        record.kind,
        *(_entry_text(record, side) or ABSENT for side in binary.SIDE_ORDER),
        record.descriptor or ABSENT,
    ]


def _column_widths(natural: list[int], max_width: int | None, minimum: list[int]) -> list[int]:
    total = sum(natural) + GAP * (len(natural) - 1)
    if max_width is None or total <= max_width:
        return natural
    # Keep the narrow Kind column, shrink the rest proportionally.
    rest_width = max_width - natural[0] - GAP * (len(natural) - 1)
    rest_natural = sum(natural[1:])
    if rest_width <= 0 or rest_natural <= 0:
        return [natural[0], *(minimum[1:])]
    scale = rest_width / rest_natural
    return [natural[0], *(max(minimum[index + 1], int(width * scale))
                          for index, width in enumerate(natural[1:]))]


def _wrap_row(row: list[str], widths: list[int]) -> list[list[str]]:
    return [textwrap.wrap(cell, width, break_on_hyphens=False) or [""] for cell, width in zip(row, widths)]


def _format_cells(cells: list[list[str]], widths: list[int], line: int) -> str:
    parts = []
    for index, cell_lines in enumerate(cells):
        text = cell_lines[line] if line < len(cell_lines) else ""
        parts.append(text.ljust(widths[index]))
    return (" " * GAP).join(parts).rstrip()


def render_table(records: list[binary.Record], max_width: int | None = None) -> str:
    rows = [_row_cells(record) for record in records]
    natural = [
        max([len(HEADERS[index]), *(len(row[index]) for row in rows)]) for index in range(len(HEADERS))
    ]
    widths = _column_widths(natural, max_width, [len(header) for header in HEADERS])

    lines = [_format_cells(_wrap_row(HEADERS, widths), widths, 0)]
    lines.append("-" * (sum(widths) + GAP * (len(widths) - 1)))
    for row in rows:
        cells = _wrap_row(row, widths)
        for line_index in range(max(len(cell_lines) for cell_lines in cells)):
            lines.append(_format_cells(cells, widths, line_index))
    return "\n".join(lines)


def render_csv(records: list[binary.Record]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(HEADERS)
    for record in records:
        writer.writerow([
            record.kind,
            *(_entry_text(record, side) or "" for side in binary.SIDE_ORDER),
            record.descriptor,
        ])
    return output.getvalue()
