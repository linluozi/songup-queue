"""Minimal, dependency-free QR code encoder (byte mode, ECC level M).

The host page has to show a scannable code for ``http://<lan-ip>:<port>`` on the
wall, and the project's hard rule is *standard library only* — the same rule
that lets it run from a USB stick on a machine with no network. So this file
exists instead of a ``qrcode`` dependency.

Scope is deliberately narrow: byte mode, ECC level M, versions 1-10 (up to 213
bytes). That covers every LAN URL and is small enough to audit.

Correctness is not argued, it is measured: ``tools/verify_qr.py`` compares the
full module matrix against the reference ``qrcode`` library for a battery of
inputs and requires **bit-identical** output, including mask selection.

Licence: MIT, same as the project.
"""

import re

# --- Tables (versions 1..10, ECC level M) ---------------------------------
#: Total codewords per version.
_TOTAL_CODEWORDS = [0, 26, 44, 70, 100, 134, 172, 196, 242, 292, 346]

#: (EC codewords per block, [(block count, data codewords per block), ...])
_ECC_M = {
    1: (10, [(1, 16)]),
    2: (16, [(1, 28)]),
    3: (26, [(1, 44)]),
    4: (18, [(2, 32)]),
    5: (24, [(2, 43)]),
    6: (16, [(4, 27)]),
    7: (18, [(4, 31)]),
    8: (22, [(2, 38), (2, 39)]),
    9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}

#: Alignment pattern centre coordinates per version.
_ALIGN = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
}

_ECC_BITS = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}


def _bch(data, poly, poly_bits):
    """Remainder of ``data << (poly_bits-1)`` divided by ``poly`` over GF(2)."""
    value = data << (poly_bits - 1)
    while value.bit_length() >= poly_bits:
        value ^= poly << (value.bit_length() - poly_bits)
    return value


def _format_bits(ecc_level, mask):
    """15-bit format information: 5 data bits + BCH(15,5), XOR 0x5412."""
    data = (_ECC_BITS[ecc_level] << 3) | mask
    return ((data << 10) | _bch(data, 0b10100110111, 11)) ^ 0b101010000010010


def _version_bits(version):
    """18-bit version information (versions 7+): 6 data bits + BCH(18,6)."""
    return (version << 12) | _bch(version, 0b1111100100101, 13)


# --- Reed-Solomon over GF(256), primitive polynomial 0x11D ---------------

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree):
    poly = [1]
    for i in range(degree):
        # multiply poly by (x - a^i)
        nxt = [0] * (len(poly) + 1)
        for j, coeff in enumerate(poly):
            nxt[j] ^= coeff
            nxt[j + 1] ^= _gf_mul(coeff, _EXP[i])
        poly = nxt
    return poly


def _rs_encode(data, ecc_len):
    gen = _rs_generator(ecc_len)
    remainder = list(data) + [0] * ecc_len
    for i in range(len(data)):
        factor = remainder[i]
        if factor == 0:
            continue
        for j, coeff in enumerate(gen):
            remainder[i + j] ^= _gf_mul(coeff, factor)
    return remainder[len(data):]


# --- Bit stream -----------------------------------------------------------


class _Bits(object):
    def __init__(self):
        self.bits = []

    def put(self, value, length):
        for i in range(length - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def __len__(self):
        return len(self.bits)


def _data_capacity(version):
    ecc_len, groups = _ECC_M[version]
    return sum(count * size for count, size in groups), ecc_len, groups


def _pick_version(payload_len):
    for version in range(1, 11):
        capacity, _, _ = _data_capacity(version)
        # 4 mode bits + 8 char-count bits (versions 1-9) or 16 (10+)
        header = 4 + (8 if version <= 9 else 16)
        if (capacity * 8) >= header + payload_len * 8:
            return version
    raise ValueError("payload too long for this encoder (%d bytes)" % payload_len)


def _build_codewords(payload, version):
    capacity, ecc_len, groups = _data_capacity(version)
    stream = _Bits()
    stream.put(0b0100, 4)  # byte mode
    stream.put(len(payload), 8 if version <= 9 else 16)
    for byte in payload:
        stream.put(byte, 8)

    data_bits = capacity * 8
    # Terminator, up to four zero bits.
    stream.put(0, min(4, data_bits - len(stream)))
    # Pad to a byte boundary.
    while len(stream) % 8:
        stream.bits.append(0)

    codewords = [
        int("".join(str(b) for b in stream.bits[i:i + 8]), 2)
        for i in range(0, len(stream.bits), 8)
    ]
    # Alternating pad bytes.
    pad = (0xEC, 0x11)
    i = 0
    while len(codewords) < capacity:
        codewords.append(pad[i % 2])
        i += 1

    # Split into blocks, compute ECC per block, then interleave.
    blocks, ecc_blocks, offset = [], [], 0
    for count, size in groups:
        for _ in range(count):
            block = codewords[offset:offset + size]
            offset += size
            blocks.append(block)
            ecc_blocks.append(_rs_encode(block, ecc_len))

    result = []
    for i in range(max(len(b) for b in blocks)):
        for block in blocks:
            if i < len(block):
                result.append(block[i])
    for i in range(ecc_len):
        for block in ecc_blocks:
            result.append(block[i])
    return result


# --- Matrix ---------------------------------------------------------------


def _new_matrix(size):
    return [[None] * size for _ in range(size)]


def _place_finder(matrix, row, col):
    """7x7 finder pattern plus its one-module separator."""
    size = len(matrix)
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            r, c = row + dr, col + dc
            if not (0 <= r < size and 0 <= c < size):
                continue
            if dr in (-1, 7) or dc in (-1, 7):
                # Separator ring: light, one module wide.
                matrix[r][c] = 0
            elif dr in (0, 6) or dc in (0, 6):
                matrix[r][c] = 1
            elif 2 <= dr <= 4 and 2 <= dc <= 4:
                matrix[r][c] = 1
            else:
                matrix[r][c] = 0


def _place_alignment(matrix, version):
    coords = _ALIGN[version]
    last = len(coords) - 1
    for i, row in enumerate(coords):
        for j, col in enumerate(coords):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue  # would collide with a finder
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    matrix[row + dr][col + dc] = 0 if max(abs(dr), abs(dc)) == 1 else 1


def _place_timing(matrix, version):
    size = len(matrix)
    for i in range(8, size - 8):
        bit = 1 if i % 2 == 0 else 0
        if matrix[6][i] is None:
            matrix[6][i] = bit
        if matrix[i][6] is None:
            matrix[i][6] = bit


def _reserve_format(matrix, version):
    """Mark the format/version areas as taken (filled with real bits later)."""
    size = len(matrix)
    for i in range(9):
        if matrix[8][i] is None:
            matrix[8][i] = 0
        if matrix[i][8] is None:
            matrix[i][8] = 0
    for i in range(8):
        if matrix[8][size - 1 - i] is None:
            matrix[8][size - 1 - i] = 0
        if matrix[size - 1 - i][8] is None:
            matrix[size - 1 - i][8] = 0
    matrix[size - 8][8] = 1  # dark module
    if version >= 7:
        for i in range(6):
            for j in range(3):
                matrix[size - 11 + j][i] = 0
                matrix[i][size - 11 + j] = 0


def _place_data(matrix, codewords):
    size = len(matrix)
    bits = []
    for byte in codewords:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)

    index = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1  # skip the vertical timing column
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if matrix[row][c] is not None:
                    continue
                matrix[row][c] = bits[index] if index < len(bits) else 0
                index += 1
        upward = not upward
        col -= 2
    return index


def _mask_bit(mask, row, col):
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row + col) % 2 + (row * col) % 3) % 2 == 0


def _function_map(version, size):
    """Boolean grid: True where the module belongs to a function pattern.

    Built from the geometry of the version rather than inferred from whatever
    happened to be written into the matrix. The earlier version of this file
    guessed from a per-size lookup and missed the off-diagonal alignment
    patterns from version 7 up, which masked 46 data modules that must not be
    masked — caught by the differential test, not by reading the spec.
    """
    fmap = [[False] * size for _ in range(size)]

    def fill(row0, col0, row1, col1):
        for r in range(max(0, row0), min(size, row1 + 1)):
            for c in range(max(0, col0), min(size, col1 + 1)):
                fmap[r][c] = True

    # Finder patterns with their one-module separators.
    fill(0, 0, 7, 7)
    fill(0, size - 8, 7, size - 1)
    fill(size - 8, 0, size - 1, 7)
    # Timing patterns.
    fill(6, 0, 6, size - 1)
    fill(0, 6, size - 1, 6)
    # Alignment patterns (skip the three that would overlap a finder).
    coords = _ALIGN[version]
    last = len(coords) - 1
    for i, row in enumerate(coords):
        for j, col in enumerate(coords):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue
            fill(row - 2, col - 2, row + 2, col + 2)
    # Format information, both copies.
    fill(8, 0, 8, 8)
    fill(0, 8, 8, 8)
    fill(8, size - 8, 8, size - 1)
    fill(size - 7, 8, size - 1, 8)
    # Version information (7 and up), both copies.
    if version >= 7:
        fill(0, size - 11, 5, size - 9)
        fill(size - 11, 0, size - 9, 5)
    # Dark module.
    fmap[size - 8][8] = True
    return fmap


def _apply_mask(matrix, mask, fmap):
    size = len(matrix)
    for row in range(size):
        for col in range(size):
            if fmap[row][col]:
                continue
            if _mask_bit(mask, row, col):
                matrix[row][col] ^= 1


def _write_format(matrix, ecc_level, mask, blank=False):
    """Write the 15 format bits in both copies.

    ``blank=True`` reproduces the reference implementation's evaluation mode,
    where the format and version areas are held at 0 while candidate masks are
    scored. The chosen mask is therefore identical to the reference's, which is
    what the differential test in ``tools/verify_qr.py`` checks.
    """
    size = len(matrix)
    bits = 0 if blank else _format_bits(ecc_level, mask)
    # bit i is the i-th least significant bit, per ISO/IEC 18004 figure 25.
    for i in range(15):
        bit = (bits >> i) & 1
        # Copy A: down column 8, skipping the timing row.
        if i < 6:
            matrix[i][8] = bit
        elif i < 8:
            matrix[i + 1][8] = bit
        else:
            matrix[size - 15 + i][8] = bit
        # Copy B: along row 8, right edge first, then around the finder.
        if i < 8:
            matrix[8][size - 1 - i] = bit
        elif i < 9:
            matrix[8][7] = bit
        else:
            matrix[8][15 - i - 1] = bit

    matrix[size - 8][8] = 0 if blank else 1  # dark module


def _write_version(matrix, version, blank=False):
    if version < 7:
        return
    size = len(matrix)
    bits = 0 if blank else _version_bits(version)
    for i in range(18):
        bit = (bits >> i) & 1
        matrix[size - 11 + i % 3][i // 3] = bit
        matrix[i // 3][size - 11 + i % 3] = bit


def _penalty(matrix):
    size = len(matrix)
    score = 0

    # Rule 1: runs of five or more.
    for line in list(matrix) + [list(col) for col in zip(*matrix)]:
        run, prev = 1, line[0]
        for value in line[1:]:
            if value == prev:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run, prev = 1, value
        if run >= 5:
            score += 3 + (run - 5)

    # Rule 2: 2x2 blocks of one colour.
    for row in range(size - 1):
        for col in range(size - 1):
            block = matrix[row][col]
            if (matrix[row][col + 1] == block
                    and matrix[row + 1][col] == block
                    and matrix[row + 1][col + 1] == block):
                score += 3

    # Rule 3: 1:1:3:1:1 finder-like pattern with four light modules beside it.
    pattern_a = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    pattern_b = list(reversed(pattern_a))
    for line in list(matrix) + [list(col) for col in zip(*matrix)]:
        for i in range(size - 10):
            window = line[i:i + 11]
            if window == pattern_a or window == pattern_b:
                score += 40

    # Rule 4: deviation from a 50% dark ratio, one step per full 5%.
    # Truncating with integer division is what the reference does; a rounded
    # version shifts the score by 10 on ties and picks a different mask.
    dark = sum(sum(row) for row in matrix)
    percent = float(dark) / (size * size)
    score += int(abs(percent * 100 - 50) / 5) * 10
    return score


def encode(text, ecc_level="M"):
    """Return the QR matrix (list of rows of 0/1) for ``text``.

    Byte mode, ECC level ``M``, version chosen automatically (1-10).
    """
    if ecc_level != "M":
        raise ValueError("this encoder only implements ECC level M")
    if not text:
        # A zero-length QR is legal but useless, and a blank code is worse than
        # an error: it renders as a plausible-looking grid that scans to nothing.
        raise ValueError("refusing to encode an empty string")
    payload = text.encode("utf-8")
    version = _pick_version(len(payload))
    size = 17 + 4 * version
    fmap = _function_map(version, size)

    codewords = _build_codewords(payload, version)

    best, best_score, best_mask = None, None, 0
    for mask in range(8):
        matrix = _new_matrix(size)
        _place_finder(matrix, 0, 0)
        _place_finder(matrix, 0, size - 7)
        _place_finder(matrix, size - 7, 0)
        _place_alignment(matrix, version)
        _place_timing(matrix, version)
        _reserve_format(matrix, version)
        # Format and version bits stay blank while masks are scored; ISO/IEC
        # 18004 §8.8.2 scores the candidate as it would ship, but the reference
        # implementation scores with those areas zeroed. Both are in the wild;
        # matching the reference keeps this file diffable against it.
        _write_format(matrix, ecc_level, mask, blank=True)
        _write_version(matrix, version, blank=True)
        _place_data(matrix, codewords)
        _apply_mask(matrix, mask, fmap)
        score = _penalty(matrix)
        if best_score is None or score < best_score:
            best, best_score, best_mask = matrix, score, mask

    # Re-render the winner with the real format/version bits.
    _write_format(best, ecc_level, best_mask)
    _write_version(best, version)
    return best


def svg(text, size=168, dark="#17110C", light="#FBF5E9", quiet=4, radius=6):
    """Render ``text`` as a standalone SVG QR code with a quiet zone."""
    matrix = encode(text)
    n = len(matrix)
    total = n + quiet * 2
    rects = []
    for row in range(n):
        for col in range(n):
            if matrix[row][col]:
                rects.append(
                    '<rect x="%d" y="%d" width="1" height="1"/>' % (col + quiet, row + quiet)
                )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" aria-label="QR code">'
        '<rect width="%d" height="%d" rx="%d" fill="%s"/>'
        '<g fill="%s" shape-rendering="crispEdges">%s</g></svg>'
        % (size, size, total, total, total, total, radius, light, dark, "".join(rects))
    )


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def module_count(text):
    """Handy for tests: how big the matrix is for ``text``."""
    return len(encode(text))
