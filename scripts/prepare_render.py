"""Prepare a detached-board render copy without modifying manufacturing files."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import re
import uuid
from collections import defaultdict

from kicad_helpers import ROOT, blocks, child, parse, value, properties


def mask_color(text, color):
    for a, b, setup in blocks(text):
        if not setup.startswith("(setup"):
            continue
        for c, d, stackup in blocks(setup):
            if not stackup.startswith("(stackup"):
                continue
            for e, f, layer in reversed(list(blocks(stackup))):
                parsed = parse(layer)
                if parsed[0] == "layer" and parsed[1] in ("F.Mask", "B.Mask"):
                    for g, h, field in reversed(list(blocks(layer))):
                        if field.startswith("(color "):
                            layer = layer[:g] + layer[h:]
                    layer = layer.rstrip()[:-1] + "\n(color " + json.dumps(color) + ")\n)"
                    stackup = stackup[:e] + layer + stackup[f:]
            setup = setup[:c] + stackup + setup[d:]
            return text[:a] + setup + text[b:]
    raise ValueError("Board stackup not found")


def prepare(target, config_file):
    target, config_file = Path(target), Path(config_file)
    if target.resolve() == (ROOT / "OpenBridge.kicad_pcb").resolve():
        raise RuntimeError("Refusing to modify the manufacturing PCB")
    config = json.loads(config_file.read_text())
    text = mask_color(target.read_text(encoding="utf-8"), config["board_color"])
    removed = []

    def inside(position):
        if position is None:
            return False
        x, y = map(float, position[:2])
        return any(x0 - 1e-5 <= x <= x1 + 1e-5 and y0 - 1e-5 <= y <= y1 + 1e-5 for x0, y0, x1, y1 in config["breakaway_regions_mm"])

    def point(node, field):
        found = child(node, field)
        return found[1:3] if found else None

    if config["remove_breakaway_strips"]:
        expected = set(config["breakaway_components"])
        edge_count = 0
        removed_stubs = set()
        stubs = config.get("breakaway_stub_edges_mm", [])
        for a, b, block in reversed(list(blocks(text))):
            node = parse(block)
            kind = node[0]
            remove = False
            if kind == "footprint":
                ref = properties(node).get("Reference", "")
                if ref in expected and not inside(point(node, "at")):
                    raise ValueError(f"{ref} moved outside the configured strip region")
                remove = ref in expected or ref.startswith("MB")
                if remove:
                    removed.append(ref)
            elif kind in ("segment", "arc"):
                remove = inside(point(node, "start")) and inside(point(node, "end"))
            elif kind == "via":
                remove = inside(point(node, "at"))
            elif kind == "zone":
                remove = value(node, "net").startswith(("/BS1_", "/BS2_", "/BS3_", "/BS4_"))
            elif kind.startswith("gr_") and value(node, "layer") == "Edge.Cuts":
                start, end = point(node, "start"), point(node, "end")
                endpoints = {tuple(map(float, p)) for p in (start, end)}
                matched_stub = next((i for i, stub in enumerate(stubs)
                                     if kind == "gr_line" and endpoints == {tuple(stub[:2]), tuple(stub[2:])}), None)
                if matched_stub is not None:
                    # This short return edge belonged to the attachment tab. Keeping
                    # it would make the new seam double back and intersect itself.
                    remove = True
                    removed_stubs.add(matched_stub)
                    edge_count += 1
                elif inside(start) and inside(end):
                    xs = [float(p[0]) for p in (start, end)]
                    on_seam = any(abs(xs[0] - seam[0]) < 1e-5 and abs(xs[1] - seam[0]) < 1e-5 for seam in config["breakaway_seams_mm"])
                    if not on_seam:
                        remove = True
                        edge_count += 1
            elif kind.startswith("gr_"):
                remove = inside(point(node, "at"))
            if remove:
                text = text[:a] + text[b:]
        if set(removed) & expected != expected:
            raise ValueError(f"Breakaway references changed: {expected - set(removed)}")
        if edge_count == 0:
            raise ValueError("No breakaway edges removed; check render configuration")
        if len(removed_stubs) != len(stubs):
            raise ValueError("Configured attachment stub edges changed; review render-config.json")
        for x0, y0, x1, y1 in config["breakaway_seams_mm"]:
            line = f'(gr_line (start {x0} {y0}) (end {x1} {y1}) (stroke (width 0.05) (type default)) (layer "Edge.Cuts") (uuid "{uuid.uuid4()}"))'
            text = text.rstrip()[:-1] + line + "\n)\n"
        # All outline vertices must have degree two and belong to one contour.
        # Round sub-micron endpoint differences already present in the source file.
        graph = defaultdict(list)
        for _, _, block in blocks(text):
            node = parse(block)
            if node[0].startswith("gr_") and value(node, "layer") == "Edge.Cuts":
                a, b = [tuple(round(float(n), 3) for n in point(node, k)) for k in ("start", "end")]
                graph[a].append(b)
                graph[b].append(a)
        seen, pending = set(), [next(iter(graph))] if graph else []
        while pending:
            vertex = pending.pop()
            if vertex not in seen:
                seen.add(vertex)
                pending.extend(graph[vertex])
        if not graph or any(len(v) != 2 for v in graph.values()) or len(seen) != len(graph):
            raise ValueError("Detached render must have exactly one closed main-board outline; review seams")

    # Resolve models before moving the PCB into the temporary directory. Fail instead
    # of silently publishing a render with missing parts.
    def resolve(match):
        path = json.loads(match[1]).replace("${KIPRJMOD}", str(ROOT))
        for name, val in os.environ.items():
            path = path.replace("${" + name + "}", val)
        if not Path(path).is_file():
            raise FileNotFoundError(f"Missing 3D model: {path}")
        return "(model " + json.dumps(Path(path).resolve().as_posix())
    text = re.sub(r'\(model\s+("(?:\\.|[^"\\])*")', resolve, text)
    target.write_text(text, encoding="utf-8")
    print(f"Prepared render copy; removed {len(removed)} strip and mouse-bite footprints")


if __name__ == "__main__":
    prepare(*sys.argv[1:3])
