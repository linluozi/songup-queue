"""Regression tests for :mod:`qrmini`, the dependency-free QR encoder.

These tests deliberately do **not** import a third-party QR library, because the
point of ``qrmini`` is that the app runs on a machine with nothing installed.
The reference comparison lives in ``tools/verify_qr.py`` and needs ``qrcode``;
that one is a development check, this one is the CI gate.

Golden hashes were produced by the reference implementation and cross-checked
module by module (see ``tools/verify_qr.py``). If a hash here changes, the
encoder changed — which may be correct, but it must be re-proven against the
reference before the hash is updated.
"""

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import qrmini  # noqa: E402


def digest(text):
    matrix = qrmini.encode(text)
    flat = "".join("".join(str(cell) for cell in row) for row in matrix)
    return len(matrix), hashlib.sha256(flat.encode("ascii")).hexdigest()


class GoldenMatrixTest(unittest.TestCase):
    """Fixed inputs must produce fixed matrices, byte for byte."""

    GOLDEN = {
        "http://192.168.1.10:5000": (25, "87f3608abd768e482f7a8ab9db59ffc654d8ffff8a35b6dc682ea17aa4c9447b"),
        "http://127.0.0.1:5066": (25, "f61561f4a8a21004edbc1384986d96a2f88a6e32c00cb59948ba0ac4313bdce3"),
        "曲票": (21, "3f7e3d550cb37c01ad98f3230e4f9dcabebfed5da786253b335e4937c5c538c2"),
    }

    def test_golden(self):
        for text, expected in self.GOLDEN.items():
            with self.subTest(text=text):
                self.assertEqual(digest(text), expected)


class StructureTest(unittest.TestCase):
    def test_size_matches_version(self):
        # A 21-module matrix is version 1; each extra version adds 4 modules.
        for text, version in (("A", 1), ("x" * 40, 3), ("x" * 120, 7)):
            with self.subTest(text=text[:8]):
                self.assertEqual(len(qrmini.encode(text)), 17 + 4 * version)

    def test_finder_patterns_present(self):
        matrix = qrmini.encode("http://192.168.1.10:5000")
        size = len(matrix)
        for row, col in ((0, 0), (0, size - 7), (size - 7, 0)):
            # Outer ring dark, inner ring light, 3x3 core dark.
            self.assertEqual(matrix[row][col], 1)
            self.assertEqual(matrix[row + 1][col + 1], 0)
            self.assertEqual(matrix[row + 3][col + 3], 1)
            self.assertEqual(matrix[row + 6][col + 6], 1)

        # The separator is the one-module light ring just outside the finder,
        # on the sides that face the data area (not the quiet zone corners).
        self.assertEqual(matrix[7][0], 0)          # below the top-left finder
        self.assertEqual(matrix[0][7], 0)          # right of the top-left finder
        self.assertEqual(matrix[7][size - 8], 0)   # below the top-right finder
        self.assertEqual(matrix[size - 8][7], 0)   # right of the bottom-left finder

    def test_dark_module(self):
        matrix = qrmini.encode("hello")
        size = len(matrix)
        self.assertEqual(matrix[size - 8][8], 1)

    def test_timing_pattern_alternates(self):
        matrix = qrmini.encode("hello")
        size = len(matrix)
        for i in range(8, size - 8):
            self.assertEqual(matrix[6][i], 1 if i % 2 == 0 else 0)
            self.assertEqual(matrix[i][6], 1 if i % 2 == 0 else 0)

    def test_not_all_dark_or_light(self):
        matrix = qrmini.encode("http://192.168.1.10:5000")
        flat = [cell for row in matrix for cell in row]
        ratio = sum(flat) / len(flat)
        # ISO/IEC 18004 mask selection targets roughly half dark.
        self.assertGreater(ratio, 0.35)
        self.assertLess(ratio, 0.65)


class BoundaryTest(unittest.TestCase):
    def test_max_payload_fits(self):
        # 213 bytes is the largest payload version 10 / ECC-M can hold in this
        # encoder's byte mode.
        matrix = qrmini.encode("x" * 213)
        self.assertEqual(len(matrix), 57)

    def test_over_capacity_raises(self):
        with self.assertRaises(ValueError):
            qrmini.encode("x" * 214)

    def test_empty_string_raises(self):
        # An empty QR is legal in the spec but useless here; make it explicit
        # rather than shipping a blank code nobody can scan.
        with self.assertRaises(ValueError):
            qrmini.encode("")

    def test_unsupported_ecc_level(self):
        with self.assertRaises(ValueError):
            qrmini.encode("x", ecc_level="H")


class SvgTest(unittest.TestCase):
    def test_self_contained(self):
        svg = qrmini.svg("http://192.168.1.10:5000")
        self.assertTrue(svg.startswith("<svg"))
        self.assertNotIn("http://", svg.replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("<image", svg)
        self.assertNotIn("xlink:href", svg)

    def test_quiet_zone_is_four_modules(self):
        text = "http://192.168.1.10:5000"
        n = qrmini.module_count(text)
        svg = qrmini.svg(text, quiet=4)
        # Every rect sits inside the quiet zone.
        for x in [part for part in svg.split("<rect x=\"")[1:]]:
            self.assertGreaterEqual(int(x.split('"')[0]), 4)
        self.assertIn('viewBox="0 0 %d %d"' % (n + 8, n + 8), svg)


if __name__ == "__main__":
    unittest.main()
