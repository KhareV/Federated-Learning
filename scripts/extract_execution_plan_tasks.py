#!/usr/bin/env python3
"""Extract the 36 canonical task packets from the authoritative execution-plan DOCX.

This is a source-reconciliation utility, not a normal later-phase runtime dependency.
The checked-in JSON snapshot is consumed by the registry generator and semantic tests.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from nhm.hashing import hash_file

ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "NHM_Solo_Implementation_Execution_Plan_v1.0.docx"
SOURCE_SHA256 = "f260a93e973161a1461497fbb4ae0194bc72f20fc47c1689e57ec6c0cd6f2696"
DEFAULT_SOURCE = ROOT / SOURCE_NAME
DEFAULT_OUTPUT = ROOT / "manifests/task_packets_v1.json"
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

FIELD_LABELS = (
    "TASK ID",
    "PHASE",
    "OBJECTIVE",
    "RELEVANT v2.2 SECTIONS",
    "PREREQUISITES",
    "FILES TO INSPECT",
    "FILES TO CREATE/MODIFY",
    "INPUTS / OUTPUTS",
    "INTERFACES / CONTRACTS",
    "IMPLEMENTATION CONSTRAINTS",
    "TESTS",
    "COMMANDS / RUN STEPS",
    "EXPECTED ARTIFACTS",
    "ACCEPTANCE CRITERIA",
    "RISKS",
    "RECOVERY",
    "WHAT MUST NOT CHANGE",
    "GATE / FREEZE IMPACT",
    "NEXT UNLOCKED DEPENDENCY",
)
FIELD_KEYS = {
    label: label.casefold().replace(" / ", "_").replace(" ", "_")
    for label in FIELD_LABELS
}
FIELD_KEYS["TASK ID"] = "packet_task_id"
HEADING = re.compile(r"^(T\d{3})\s+—\s+(.+)$")


def document_xml(path: Path) -> ElementTree.Element:
    with zipfile.ZipFile(path) as archive:
        return ElementTree.fromstring(archive.read("word/document.xml"))


def docx_lines(document: ElementTree.Element) -> list[str]:
    paragraphs = document.iter(f"{{{WORD_NAMESPACE}}}p")
    lines = []
    for paragraph in paragraphs:
        text = "".join(
            node.text or "" for node in paragraph.iter(f"{{{WORD_NAMESPACE}}}t")
        ).strip()
        if text:
            lines.append(text)
    return lines


def docx_tables(document: ElementTree.Element) -> list[list[list[str]]]:
    tables = []
    for table in document.iter(f"{{{WORD_NAMESPACE}}}tbl"):
        rows = []
        for row in table.findall(f"{{{WORD_NAMESPACE}}}tr"):
            cells = []
            for cell in row.findall(f"{{{WORD_NAMESPACE}}}tc"):
                paragraphs = []
                for paragraph in cell.iter(f"{{{WORD_NAMESPACE}}}p"):
                    text = "".join(
                        node.text or ""
                        for node in paragraph.iter(f"{{{WORD_NAMESPACE}}}t")
                    ).strip()
                    if text:
                        paragraphs.append(text)
                cells.append(" ".join(paragraphs))
            rows.append(cells)
        tables.append(rows)
    return tables


def extract_packets(lines: list[str]) -> list[dict[str, str]]:
    starts = [index for index, line in enumerate(lines) if HEADING.fullmatch(line)]
    packets: list[dict[str, str]] = []
    for position, start in enumerate(starts):
        match = HEADING.fullmatch(lines[start])
        if match is None:
            raise AssertionError("Task heading unexpectedly failed to parse")
        task_id, task_name = match.groups()
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        segment = lines[start + 1 : end]
        if "TASK ID" not in segment:
            continue
        packet: dict[str, str] = {"task_id": task_id, "task_name": task_name}
        for field_index, label in enumerate(FIELD_LABELS):
            try:
                value_start = segment.index(label) + 1
            except ValueError as error:
                raise RuntimeError(f"{task_id} missing packet field {label}") from error
            later_positions = [
                segment.index(later)
                for later in FIELD_LABELS[field_index + 1 :]
                if later in segment
            ]
            value_end = min(later_positions, default=len(segment))
            packet[FIELD_KEYS[label]] = " ".join(segment[value_start:value_end]).strip()
        if packet["task_id"] != packet["packet_task_id"]:
            raise RuntimeError(f"heading/body task ID mismatch for {task_id}")
        del packet["packet_task_id"]
        packets.append(packet)
    return packets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    actual_hash = hash_file(args.source)
    if actual_hash != SOURCE_SHA256:
        raise SystemExit(
            f"SOURCE_VERSION_CONFLICT: expected {SOURCE_SHA256}, found {actual_hash}"
        )
    document = document_xml(args.source)
    packets = extract_packets(docx_lines(document))
    expected_ids = [f"T{number:03d}" for number in range(1, 37)]
    if [packet["task_id"] for packet in packets] != expected_ids:
        raise SystemExit(
            "execution-plan task extraction is not exactly T001-T036: "
            f"{[packet['task_id'] for packet in packets]}"
        )
    requirement_table = next(
        table
        for table in docx_tables(document)
        if table and table[0][:3] == ["ID", "Locked requirement", "Task(s)"]
    )
    requirement_task_map = {
        row[0]: row[2].replace(",", ";") for row in requirement_table[1:] if row[0]
    }
    if set(requirement_task_map) != {f"R{number:02d}" for number in range(1, 29)}:
        raise SystemExit("execution-plan requirement map is not exactly R01-R28")

    payload = {
        "snapshot_version": "1.0",
        "source_document": SOURCE_NAME,
        "source_role": "implementation_sequencing_authority",
        "source_sha256": actual_hash,
        "source_locator": "Section 22 — Primary Implementation Task Packets",
        "packet_count": len(packets),
        "requirement_task_map": requirement_task_map,
        "packets": packets,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(f"Canonical execution-plan task packets: {len(packets)}")


if __name__ == "__main__":
    main()
