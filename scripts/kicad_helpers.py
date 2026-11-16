"""Small, dependency-free helpers shared by the project maintenance scripts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[^\s()]+|[()]', text)
    stack = [[]]
    for token in tokens:
        if token == "(":
            node = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise ValueError("Unbalanced KiCad file")
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError("Unbalanced KiCad file")
    return stack[0][0]


def children(node, name):
    return [x for x in node if isinstance(x, list) and x and x[0] == name]


def child(node, name, default=None):
    return next(iter(children(node, name)), default)


def value(node, name, default=""):
    item = child(node, name)
    return item[1] if item and len(item) > 1 else default


def properties(node):
    return {p[1]: p[2] for p in children(node, "property")}


def blocks(text):
    """Yield spans of direct child expressions, preserving untouched source text."""
    depth = 0
    quoted = escaped = False
    start = 0
    for i, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
            if depth == 2:
                start = i
        elif char == ")":
            if depth == 2:
                yield start, i + 1, text[start:i + 1]
            depth -= 1
    if depth or quoted:
        raise ValueError("Unbalanced KiCad file")


def schematic_parts(path=ROOT / "OpenBridge.kicad_sch", ancestors=()):
    path = Path(path).resolve()
    if path in ancestors:
        raise ValueError(f"Recursive schematic sheet: {path}")
    doc = parse(path.read_text(encoding="utf-8"))
    for symbol in children(doc, "symbol"):
        if child(symbol, "lib_id"):
            yield path, symbol, properties(symbol)
    for sheet in children(doc, "sheet"):
        yield from schematic_parts(path.parent / properties(sheet)["Sheetfile"], (*ancestors, path))


def cli_path(explicit=None):
    candidates = [explicit, os.environ.get("KICAD_CLI"), shutil.which("kicad-cli")]
    if os.name == "nt":
        candidates += sorted(Path(os.environ.get("ProgramFiles", "C:/Program Files"), "KiCad").glob("*/bin/kicad-cli.exe"), reverse=True)
    candidates += [Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            result = subprocess.run([str(candidate), "version"], capture_output=True, text=True)
            version = re.search(r"(\d+)\.\d+", result.stdout)
            if result.returncode == 0 and version and int(version[1]) >= 10:
                return Path(candidate).resolve()
    raise RuntimeError("KiCad 10+ is required. Set KICAD_CLI or pass --kicad-cli.")


def model_directory(cli):
    candidates = [os.environ.get("KICAD10_3DMODEL_DIR"), cli.parent.parent / "share/kicad/3dmodels", Path("/usr/share/kicad/3dmodels")]
    if os.name == "nt":
        candidates += sorted(cli.parent.parent.parent.glob("*/share/kicad/3dmodels"), reverse=True)
    candidates += [Path("/Library/Application Support/kicad/3dmodels"), Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels")]
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return str(Path(candidate).resolve())
    raise RuntimeError("Install KiCad's standard 3D models or set KICAD10_3DMODEL_DIR.")


def run(args, **kwargs):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args[0]} {' '.join(map(str, args[1:]))}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def write_if_changed(path, data):
    path = Path(path)
    data = data.encode("utf-8") if isinstance(data, str) else data
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
