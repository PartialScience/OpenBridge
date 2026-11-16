"""Audit schematic/PCB purchasing coverage and export a BOM for one assembly."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import io
import re

from kicad_helpers import ROOT, child, children, parse, properties, schematic_parts, value, write_if_changed


def natural(text):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", text)]


def audit(output=ROOT / "docs/bom.csv"):
    board = parse((ROOT / "OpenBridge.kicad_pcb").read_text(encoding="utf-8"))
    footprint_list = children(board, "footprint")
    footprints = {properties(f).get("Reference"): f for f in footprint_list}
    if len(footprints) != len(footprint_list):
        raise ValueError("Duplicate PCB footprint references")
    seen = set()
    groups = defaultdict(list)
    errors = []
    board_refs = set()
    generic = []
    for file, symbol, props in schematic_parts():
        ref = props.get("Reference", "")
        if not ref or ref in seen:
            errors.append(f"Missing or duplicate schematic reference: {ref!r}")
        seen.add(ref)
        if value(symbol, "on_board") == "yes" and not ref.startswith("#"):
            board_refs.add(ref)
            footprint = footprints.get(ref)
            if footprint is None:
                errors.append(f"{ref}: on-board symbol has no PCB footprint")
            else:
                if footprint[1] != props.get("Footprint"):
                    errors.append(f"{ref}: PCB and schematic footprint assignments differ")
                if value(footprint, "path").split("/")[-1] != value(symbol, "uuid"):
                    errors.append(f"{ref}: PCB and schematic UUIDs differ")
                if properties(footprint).get("Value") != props.get("Value"):
                    errors.append(f"{ref}: PCB and schematic values differ")
        if value(symbol, "in_bom") != "yes" or ref.startswith("#") or value(symbol, "dnp") == "yes":
            continue
        for name in ("Value", "Manufacturer", "MPN", "Description"):
            if not props.get(name, "").strip():
                errors.append(f"{ref}: missing {name}")
        if props.get("Manufacturer") == "Generic":
            if props.get("MPN") != "Unspecified":
                errors.append(f"{ref}: generic parts must explicitly identify unspecified MPNs")
            generic.append(ref)
        elif props.get("MPN", "").lower() in ("tbd", "unspecified", "unknown"):
            errors.append(f"{ref}: purchased part needs a manufacturer part number")
        key = tuple(props.get(k, "") for k in ("Value", "Manufacturer", "MPN", "Footprint", "Description", "Mouser", "Datasheet"))
        groups[key].append(ref)
    for ref, footprint in footprints.items():
        attrs = child(footprint, "attr", [])
        if ref not in board_refs and "board_only" not in attrs:
            errors.append(f"{ref}: PCB footprint has no on-board schematic symbol")
    if errors:
        raise ValueError("BOM audit failed:\n" + "\n".join(errors))
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["References", "Quantity", "Value", "Manufacturer", "MPN", "Footprint", "Description", "Mouser", "Datasheet"])
    for fields, refs in sorted(groups.items(), key=lambda row: natural(sorted(row[1], key=natural)[0])):
        writer.writerow([", ".join(sorted(refs, key=natural)), len(refs), *fields])
    write_if_changed(output, stream.getvalue())
    count = sum(map(len, groups.values()))
    print(f"BOM: {count} items in {len(groups)} groups; {len(generic)} explicitly generic items; all {len(board_refs)} PCB references matched")
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=str, default=str(ROOT / "docs/bom.csv"))
    args = parser.parse_args()
    audit(args.output)
