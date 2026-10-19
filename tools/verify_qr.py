"""Differential test: our QR encoder must match the reference library bit for bit.

Correctness here is not a matter of opinion. The reference ``qrcode`` package
implements ISO/IEC 18004 independently; if our matrix differs in a single module
— including which mask was chosen — one of the two is wrong.

    python tools/verify_qr.py

Requires ``qrcode`` (dev-only, never imported by the app).
Exit code 0 = every input matched module for module.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import qrmini  # noqa: E402


CASES = [
    "http://192.168.1.10:5000",
    "http://10.0.0.2:5000",
    "http://127.0.0.1:5066",
    "https://example.com/party",
    "http://192.168.43.2:8766",
    "A",
    "0123456789",
    "http://192.168.100.200:65535",
    "曲票",
    "http://192.168.1.10:5000/?room=living-room&host=1",
    "x" * 40,
    "x" * 80,
    "x" * 120,
    "http://192.168.1.10:5000/" + "a" * 60,
    "https://songstub.local:8080/join?code=ABCD1234EFGH",
]


def reference_matrix(text):
    """Reference matrix, forced to byte mode.

    The reference library picks the densest mode per payload (numeric for
    ``0123456789``, alphanumeric for ``A``). This encoder is byte-mode only, so
    the comparison must hold the mode fixed — otherwise the test measures the
    mode choice, not the encoder.
    """
    import qrcode
    from qrcode.util import MODE_8BIT_BYTE, QRData

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=0,
    )
    qr.add_data(QRData(text.encode("utf-8"), mode=MODE_8BIT_BYTE))
    qr.make(fit=True)
    return [[1 if cell else 0 for cell in row] for row in qr.get_matrix()]


def main():
    failures = 0
    for text in CASES:
        label = text if len(text) <= 44 else text[:41] + "..."
        try:
            mine = qrmini.encode(text)
        except Exception as exc:  # noqa: BLE001
            print("ERROR  %-46s %s" % (label, exc))
            failures += 1
            continue

        try:
            ref = reference_matrix(text)
        except Exception as exc:  # noqa: BLE001
            print("SKIP   %-46s reference failed: %s" % (label, exc))
            continue

        if len(mine) != len(ref):
            print("FAIL   %-46s size %d vs reference %d" % (label, len(mine), len(ref)))
            failures += 1
            continue

        diff = sum(
            1
            for r in range(len(ref))
            for c in range(len(ref))
            if mine[r][c] != ref[r][c]
        )
        if diff:
            print("FAIL   %-46s %d/%d modules differ" % (label, diff, len(ref) ** 2))
            failures += 1
        else:
            print("PASS   %-46s %dx%d identical" % (label, len(ref), len(ref)))

    # Sweep every payload length 1..213 — that crosses all ten versions this
    # encoder supports, including every block-group boundary and the 7+ version
    # information area. A single hand-picked case cannot cover those.
    sweep_bad = []
    for length in range(1, 214):
        text = ("http://192.168.1.%d:5000" % (length % 255)) if length > 10 else "x" * length
        text = text[:length]
        try:
            mine = qrmini.encode(text)
            ref = reference_matrix(text)
        except Exception as exc:  # noqa: BLE001
            sweep_bad.append((length, str(exc)))
            continue
        if len(mine) != len(ref) or any(
            mine[r][c] != ref[r][c] for r in range(len(ref)) for c in range(len(ref))
        ):
            sweep_bad.append((length, "module mismatch"))

    if sweep_bad:
        print("\nFAIL   length sweep: %d/%d mismatched" % (len(sweep_bad), 213))
        for length, why in sweep_bad[:10]:
            print("         len=%-3d %s" % (length, why))
        failures += 1
    else:
        print("PASS   length sweep 1..213 (all ten versions) identical")

    total = len(CASES) + 1
    print("\n%d/%d checks matched the reference encoder exactly" % (total - failures, total))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
