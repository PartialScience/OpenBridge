"""Integration checks for render-only geometry edits; no third-party Python packages."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from kicad_helpers import ROOT, child, children, cli_path, model_directory, parse, properties
from prepare_render import prepare
from update_previews import pcb_preview, validate_render_outline


class RenderCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / "OpenBridge.kicad_pcb"
        cls.original = cls.source.read_bytes()
        cls.board = parse(cls.original.decode())
        cls.config = json.loads((ROOT / "scripts/render-config.json").read_text())
        cls.cli = cli_path()
        os.environ["KICAD10_3DMODEL_DIR"] = model_directory(cls.cli)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="openbridge-test-")
        self.directory = Path(self.temporary.name)
        self.target = self.directory / "render.kicad_pcb"
        self.target.write_bytes(self.original)

    def tearDown(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.temporary.cleanup()

    def render_copy(self, config):
        path = self.directory / "config.json"
        path.write_text(json.dumps(config))
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(self.target, path)
        return parse(self.target.read_text())

    def test_detached_copy_preserves_main_components_and_copper_pads(self):
        result = self.render_copy(self.config)
        before = {properties(f)["Reference"]: f for f in children(self.board, "footprint")}
        after = {properties(f)["Reference"]: f for f in children(result, "footprint")}
        expected_removed = set(self.config["breakaway_components"]) | {r for r in before if r.startswith("MB")}
        self.assertEqual(set(before) - set(after), expected_removed)
        self.assertEqual(len(expected_removed), 28)
        for ref, footprint in after.items():
            self.assertEqual(child(footprint, "at"), child(before[ref], "at"), ref)
            self.assertEqual(children(footprint, "pad"), children(before[ref], "pad"), ref)
        stackup = child(child(result, "setup"), "stackup")
        masks = [layer for layer in children(stackup, "layer") if layer[1] in ("F.Mask", "B.Mask")]
        self.assertEqual([child(layer, "color")[1] for layer in masks], ["Black", "Black"])
        validate_render_outline(self.cli, self.target)

    def test_connected_but_self_intersecting_seam_is_rejected_by_kicad(self):
        # Regression: the old seam doubled back over a 0.06 mm attachment stub.
        # Its endpoints form a closed loop, so the inexpensive graph check passes.
        config = {**self.config, "breakaway_stub_edges_mm": [],
                  "breakaway_seams_mm": [*self.config["breakaway_seams_mm"][:-1],
                                          [130.81, 135.66, 130.81, 138.66]]}
        self.render_copy(config)
        with self.assertRaisesRegex(ValueError, "KiCad rejected the render outline"):
            validate_render_outline(self.cli, self.target)

    def test_pcb_preview_keeps_native_portrait_orientation(self):
        source = self.directory / "pcb.svg"
        source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="20mm" viewBox="0 0 10 20"><path d="M 2 3 L 8 15"/></svg>')
        preview = pcb_preview(source)
        self.assertIn('width="10mm" height="20mm" viewBox="0 0 10 20"', preview)
        self.assertIn('d="M 2 3 L 8 15"', preview)
        self.assertNotIn('rotate(', preview)

    def test_full_panel_option_preserves_edges_tracks_and_zones(self):
        config = {**self.config, "remove_breakaway_strips": False, "board_color": "#182230"}
        result = self.render_copy(config)
        for kind in ("gr_line", "gr_arc", "segment", "arc", "via", "zone"):
            self.assertEqual(children(result, kind), children(self.board, kind), kind)
        self.assertEqual(len(children(result, "footprint")), len(children(self.board, "footprint")))

    def test_changed_attachment_geometry_fails_instead_of_guessing(self):
        config = {**self.config, "breakaway_seams_mm": self.config["breakaway_seams_mm"][:-1]}
        with self.assertRaisesRegex(ValueError, "one closed main-board outline"):
            self.render_copy(config)

    def test_source_path_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "manufacturing PCB"):
            prepare(self.source, ROOT / "scripts/render-config.json")


if __name__ == "__main__":
    unittest.main()
