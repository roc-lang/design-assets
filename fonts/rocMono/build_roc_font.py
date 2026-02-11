#!/usr/bin/env python3
"""
Build a syntax-highlighting font for the Roc programming language.

Takes any monospace font and produces a version with built-in syntax highlighting
using OpenType COLRv0 colored glyphs and `calt` contextual alternates.

Usage:
    python build_roc_font.py input.ttf -o RocMono.woff2

Dependencies:
    pip install fonttools[woff]
"""

import argparse
import copy
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeatures
from fontTools.ttLib.tables.C_P_A_L_ import table_C_P_A_L_ as CPALTable
from fontTools.colorLib.builder import buildCOLR


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Category suffixes and their palette color indices
CATEGORIES = {
    "kw":  1,  # keywords
    "op":  2,  # operators
    "cm":  3,  # comments
    "ty":  4,  # types
    "str": 5,  # strings
    "num": 6,  # numbers
}

# Light palette (index 0) — matches snapshot.css
# Dark palette (index 1) — One Dark inspired
PALETTES = [
    # Light: base, kw, op, cm, ty, str, num
    [
        (0x38, 0x3A, 0x42, 0xFF),  # base text
        (0x00, 0x00, 0xFF, 0xFF),  # keywords — blue
        (0x80, 0x00, 0x80, 0xFF),  # operators — purple
        (0x00, 0x80, 0x00, 0xFF),  # comments — green
        (0xC1, 0x84, 0x01, 0xFF),  # types — dark yellow
        (0x00, 0x80, 0x00, 0xFF),  # strings — green
        (0xFF, 0x8C, 0x00, 0xFF),  # numbers — dark orange
    ],
    # Dark:
    [
        (0xAB, 0xB2, 0xBF, 0xFF),  # base text
        (0xC6, 0x78, 0xDD, 0xFF),  # keywords — purple
        (0x56, 0xB6, 0xC2, 0xFF),  # operators — cyan
        (0x5C, 0x63, 0x70, 0xFF),  # comments — grey
        (0xE5, 0xC0, 0x7B, 0xFF),  # types — yellow
        (0x98, 0xC3, 0x79, 0xFF),  # strings — green
        (0xD1, 0x9A, 0x66, 0xFF),  # numbers — orange
    ],
]

# Keywords from tokenize.zig:372-407 (sorted longest-first for processing)
KEYWORDS = sorted([
    "and", "app", "as", "crash", "dbg", "else", "expect", "exposes",
    "exposing", "for", "generates", "has", "hosted", "if", "implements",
    "import", "imports", "in", "interface", "match", "module", "or",
    "package", "packages", "platform", "provides", "requires", "return",
    "targets", "var", "where", "while", "with", "break",
], key=lambda w: -len(w))

# Multi-char operators (order matters: longer first)
MULTI_OPS = [
    "...", "..", "->", "=>", "|>", "==", "!=", "<=", ">=",
    ":=", "::", "//", "??", ".*",
]

# Single-char operators
SINGLE_OPS = list("+-*/%^&\\|<>=!")

# ASCII chars we create alternates for (printable ASCII 0x20-0x7E)
ASCII_RANGE = range(0x20, 0x7F)


def char_to_glyph_name(font, ch):
    """Get the glyph name for a character in the font."""
    cmap = font.getBestCmap()
    return cmap.get(ord(ch))


def get_all_ascii_glyph_names(font):
    """Get glyph names for all printable ASCII chars present in the font."""
    cmap = font.getBestCmap()
    result = {}
    for code in ASCII_RANGE:
        gname = cmap.get(code)
        if gname:
            result[chr(code)] = gname
    return result


def create_alternate_glyphs(font, ascii_glyphs):
    """Create empty alternate glyphs for each category.

    Returns a dict: {category: {char: alt_glyph_name}}
    """
    glyf_table = font.get("glyf")
    hmtx = font["hmtx"]
    glyph_order = font.getGlyphOrder()

    alternates = {cat: {} for cat in CATEGORIES}

    for ch, base_name in ascii_glyphs.items():
        # Get base glyph metrics
        base_width = hmtx[base_name][0]

        for cat in CATEGORIES:
            alt_name = f"{base_name}.{cat}"
            alternates[cat][ch] = alt_name

            # Add to glyph order
            glyph_order.append(alt_name)

            # Create empty glyph with same metrics
            if glyf_table is not None:
                # TrueType outlines
                from fontTools.ttLib.tables._g_l_y_f import Glyph
                glyf_table[alt_name] = Glyph()
            # For CFF fonts, we'll handle differently below

            # Set metrics (same advance width, zero lsb)
            hmtx[alt_name] = (base_width, 0)

    font.setGlyphOrder(glyph_order)

    # Handle CFF fonts
    if "CFF " in font:
        from fontTools.cffLib import CFFFontDict
        cff = font["CFF "]
        top_dict = cff.cff.topDictIndex[0]
        char_strings = top_dict.CharStrings
        # Create empty charstrings for alternates
        for cat in CATEGORIES:
            for ch, alt_name in alternates[cat].items():
                base_name = ascii_glyphs[ch]
                # Create minimal empty charstring
                char_strings[alt_name] = copy.deepcopy(char_strings[".notdef"])

    if "CFF2" in font:
        cff2 = font["CFF2"]
        top_dict = cff2.cff.topDictIndex[0]
        char_strings = top_dict.CharStrings
        for cat in CATEGORIES:
            for ch, alt_name in alternates[cat].items():
                char_strings[alt_name] = copy.deepcopy(char_strings[".notdef"])

    return alternates


def build_cpal(font):
    """Build CPAL table with light and dark palettes."""
    from fontTools.ttLib.tables.C_P_A_L_ import Color

    cpal = CPALTable()
    cpal.version = 0
    cpal.numPaletteEntries = len(PALETTES[0])

    cpal.palettes = []
    for palette_colors in PALETTES:
        palette = []
        for r, g, b, a in palette_colors:
            palette.append(Color(blue=b, green=g, red=r, alpha=a))
        cpal.palettes.append(palette)

    font["CPAL"] = cpal


def build_colr(font, ascii_glyphs, alternates):
    """Build COLRv0 table mapping alternates to base outlines + palette colors."""
    color_layers = {}

    for cat, color_idx in CATEGORIES.items():
        for ch, alt_name in alternates[cat].items():
            base_name = ascii_glyphs[ch]
            # COLRv0: each colored glyph is a list of (glyph, paletteIndex) layers
            color_layers[alt_name] = [(base_name, color_idx)]

    # Also color base glyphs with palette index 0 (base text color)
    for ch, base_name in ascii_glyphs.items():
        color_layers[base_name] = [(base_name, 0)]

    font["COLR"] = buildCOLR(color_layers, version=0)


def glyph_name_for_char(ch):
    """Get the standard glyph name for a character."""
    # fontTools uses AGL names
    from fontTools.agl import UV2AGL
    code = ord(ch)
    return UV2AGL.get(code, f"uni{code:04X}")


def generate_feature_code(font, ascii_glyphs, alternates):
    """Generate OpenType feature code for calt-based syntax highlighting."""
    lines = []

    # Collect all glyph names we need
    all_base = sorted(set(ascii_glyphs.values()))

    # Build glyph classes
    ident_chars = []  # a-z, A-Z, 0-9, _
    upper_chars = []
    lower_chars = []
    digit_chars = []
    all_chars = []

    for ch, gname in sorted(ascii_glyphs.items()):
        all_chars.append(gname)
        if ch.isalpha() or ch == '_' or ch.isdigit():
            ident_chars.append(gname)
        if ch.isupper():
            upper_chars.append(gname)
        if ch.islower():
            lower_chars.append(gname)
        if ch.isdigit():
            digit_chars.append(gname)

    # For each category, build class of all alternates
    cat_all = {}
    for cat in CATEGORIES:
        cat_glyphs = sorted(set(alternates[cat].values()))
        cat_all[cat] = cat_glyphs

    # Helper to get glyph name for a character
    def g(ch):
        return ascii_glyphs.get(ch)

    def alt(ch, cat):
        return alternates[cat].get(ch)

    # --- Glyph classes ---
    def class_def(name, glyphs):
        if not glyphs:
            return ""
        return f"@{name} = [{' '.join(glyphs)}];"

    lines.append("# Glyph classes for Roc syntax highlighting")
    lines.append("")
    lines.append(class_def("All", all_chars))
    lines.append(class_def("IdentChar", ident_chars))
    lines.append(class_def("Upper", upper_chars))
    lines.append(class_def("Lower", lower_chars))
    lines.append(class_def("Digit", digit_chars))
    lines.append("")

    # All-category classes (base + all alternates for that category)
    for cat in CATEGORIES:
        lines.append(class_def(f"All_{cat}", cat_all[cat]))

    lines.append("")

    # Classes for category-specific variants of @All
    for cat in CATEGORIES:
        cat_glyphs = [alternates[cat].get(ch) for ch in sorted(ascii_glyphs.keys())
                      if alternates[cat].get(ch)]
        lines.append(class_def(f"AllAs_{cat}", cat_glyphs))

    lines.append("")

    # Ident chars in each category
    for cat in CATEGORIES:
        cat_ident = [alternates[cat].get(ch) for ch in sorted(ascii_glyphs.keys())
                     if ch.isalpha() or ch == '_' or ch.isdigit()
                     if alternates[cat].get(ch)]
        lines.append(class_def(f"IdentChar_{cat}", cat_ident))

    lines.append("")

    # --- Per-letter substitution lookups (reused across keywords) ---
    # We need a lookup for each letter that substitutes base -> .kw variant
    kw_letters = set()
    for kw in KEYWORDS:
        for ch in kw:
            kw_letters.add(ch)

    for ch in sorted(kw_letters):
        base = g(ch)
        kw_alt = alt(ch, "kw")
        if base and kw_alt:
            lines.append(f"lookup SUB_{ch.upper()}_KW {{")
            lines.append(f"    sub {base} by {kw_alt};")
            lines.append(f"}} SUB_{ch.upper()}_KW;")
            lines.append("")

    # Per-letter substitution lookups for operators
    op_chars = set()
    for op in MULTI_OPS:
        for ch in op:
            op_chars.add(ch)
    for ch in SINGLE_OPS:
        op_chars.add(ch)

    for ch in sorted(op_chars):
        base = g(ch)
        op_alt = alt(ch, "op")
        if base and op_alt:
            lines.append(f"lookup SUB_{_lookup_name(ch)}_OP {{")
            lines.append(f"    sub {base} by {op_alt};")
            lines.append(f"}} SUB_{_lookup_name(ch)}_OP;")
            lines.append("")

    # --- Main calt feature ---
    lines.append("feature calt {")
    lines.append("")

    # === 1. COMMENTS (highest priority) ===
    lines.append("    # --- Comments ---")
    hash_base = g('#')
    hash_cm = alt('#', 'cm')
    if hash_base and hash_cm:
        lines.append(f"    lookup Comment_Start {{")
        lines.append(f"        sub {hash_base} by {hash_cm};")
        lines.append(f"    }} Comment_Start;")
        lines.append("")
        lines.append(f"    lookup Comment_Propagate {{")
        lines.append(f"        sub {hash_cm} @All' by @AllAs_cm;")
        # Propagate from any .cm glyph
        lines.append(f"        sub @All_cm @All' by @AllAs_cm;")
        lines.append(f"    }} Comment_Propagate;")
    lines.append("")

    # === 2. STRINGS ===
    lines.append("    # --- Strings ---")
    quote_base = g('"')
    quote_str = alt('"', 'str')
    backslash_str = alt('\\', 'str')
    if quote_base and quote_str:
        lines.append(f"    lookup String_Start {{")
        lines.append(f"        sub {quote_base} by {quote_str};")
        lines.append(f"    }} String_Start;")
        lines.append("")
        lines.append(f"    lookup String_Propagate {{")
        # Continue propagation from string glyphs
        lines.append(f"        sub @All_str @All' by @AllAs_str;")
        lines.append(f"    }} String_Propagate;")
        lines.append("")
        # Stop at closing quote: un-substitute quotedbl.str back to quotedbl
        # after an even number of string chars (but NOT after backslash)
        # Use inner lookup + ignore sub (can't mix rule types in named lookup)
        lines.append(f"    lookup String_Close_Inner {{")
        lines.append(f"        sub {quote_str} by {quote_base};")
        lines.append(f"    }} String_Close_Inner;")
        lines.append("")
        lines.append(f"    lookup String_Close {{")
        if backslash_str:
            lines.append(f"        ignore sub {backslash_str} {quote_str}';")
        lines.append(f"        sub {quote_str}' lookup String_Close_Inner;")
        lines.append(f"    }} String_Close;")
    lines.append("")

    # === 3. KEYWORDS ===
    lines.append("    # --- Keywords ---")
    lines.append(f"    lookup Keywords {{")
    for kw in KEYWORDS:
        kw_glyphs = [g(ch) for ch in kw]
        if not all(kw_glyphs):
            continue

        # ignore sub when preceded by ident char
        lines.append(f"        # {kw}")
        lines.append(f"        ignore sub @IdentChar {kw_glyphs[0]}';")
        # ignore sub when followed by ident char
        lines.append(f"        ignore sub {kw_glyphs[0]}' {' '.join(kw_glyphs[1:])} @IdentChar;")

        # The actual substitution using per-letter lookups
        sub_parts = []
        for ch in kw:
            sub_parts.append(f"{g(ch)}' lookup SUB_{ch.upper()}_KW")
        lines.append(f"        sub {' '.join(sub_parts)};")
        lines.append("")

    lines.append(f"    }} Keywords;")
    lines.append("")

    # === 4. MULTI-CHAR OPERATORS ===
    lines.append("    # --- Multi-char operators ---")
    lines.append(f"    lookup MultiOps {{")
    for op in MULTI_OPS:
        op_glyphs = [g(ch) for ch in op]
        if not all(op_glyphs):
            continue

        sub_parts = []
        for ch in op:
            sub_parts.append(f"{g(ch)}' lookup SUB_{_lookup_name(ch)}_OP")
        lines.append(f"        # {op}")
        lines.append(f"        sub {' '.join(sub_parts)};")

    lines.append(f"    }} MultiOps;")
    lines.append("")

    # === 5. SINGLE-CHAR OPERATORS ===
    lines.append("    # --- Single-char operators ---")
    # Each operator with ignore rules needs separate lookups because
    # ignore sub (chaining context) and sub X by Y (single sub) can't mix
    # in a named lookup.
    for ch in SINGLE_OPS:
        base = g(ch)
        op_alt = alt(ch, "op")
        if not base or not op_alt:
            continue

        ignores = _get_single_op_ignores(ch, ascii_glyphs)
        lname = _lookup_name(ch)

        if ignores:
            # Use the existing per-char OP lookup as the inner sub
            lines.append(f"    lookup SingleOp_{lname} {{")
            for ign in ignores:
                lines.append(f"        {ign}")
            lines.append(f"        sub {base}' lookup SUB_{lname}_OP;")
            lines.append(f"    }} SingleOp_{lname};")
        else:
            # No ignores needed, simple substitution via per-char lookup
            lines.append(f"    lookup SingleOp_{lname} {{")
            lines.append(f"        sub {base}' lookup SUB_{lname}_OP;")
            lines.append(f"    }} SingleOp_{lname};")
        lines.append("")
    lines.append("")

    # === 6. TYPES (uppercase identifiers) ===
    lines.append("    # --- Types ---")
    # Inner lookup: simple substitution of uppercase letters to .ty
    lines.append(f"    lookup Types_Sub {{")
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        base = g(ch)
        ty_alt = alt(ch, "ty")
        if base and ty_alt:
            lines.append(f"        sub {base} by {ty_alt};")
    lines.append(f"    }} Types_Sub;")
    lines.append("")
    # Outer lookup: ignore if preceded by ident char, then delegate
    lines.append(f"    lookup Types_Start {{")
    lines.append(f"        ignore sub @IdentChar @Upper';")
    lines.append(f"        sub @Upper' lookup Types_Sub;")
    lines.append(f"    }} Types_Start;")
    lines.append("")

    lines.append(f"    lookup Types_Propagate {{")
    # Propagate through identifier characters after a .ty glyph
    lines.append(f"        sub @All_ty @IdentChar' by @IdentChar_ty;")
    lines.append(f"        sub @IdentChar_ty @IdentChar' by @IdentChar_ty;")
    lines.append(f"    }} Types_Propagate;")
    lines.append("")

    # === 7. NUMBERS ===
    lines.append("    # --- Numbers ---")
    # Inner lookup: simple digit substitution
    lines.append(f"    lookup Numbers_Sub {{")
    for ch in "0123456789":
        base = g(ch)
        num_alt = alt(ch, "num")
        if base and num_alt:
            lines.append(f"        sub {base} by {num_alt};")
    lines.append(f"    }} Numbers_Sub;")
    lines.append("")
    # Outer lookup: ignore if preceded by ident char
    lines.append(f"    lookup Numbers_Start {{")
    lines.append(f"        ignore sub @IdentChar @Digit';")
    lines.append(f"        sub @Digit' lookup Numbers_Sub;")
    lines.append(f"    }} Numbers_Start;")
    lines.append("")

    # Number continuation: digits, underscore, x, o, b, period, a-f (for hex)
    num_continue_chars = set("0123456789_xXoObBaAbBcCdDeEfF.")
    lines.append(f"    lookup Numbers_Propagate {{")
    for ch in sorted(num_continue_chars):
        base = g(ch)
        num_alt = alt(ch, "num")
        if base and num_alt:
            lines.append(f"        sub @All_num {base}' by {num_alt};")
            lines.append(f"        sub @IdentChar_num {base}' by {num_alt};")
    lines.append(f"    }} Numbers_Propagate;")
    lines.append("")

    lines.append("} calt;")

    return "\n".join(lines)


def _lookup_name(ch):
    """Generate a safe lookup name component for a character."""
    names = {
        '+': 'PLUS', '-': 'MINUS', '*': 'STAR', '/': 'SLASH',
        '%': 'PERCENT', '^': 'CARET', '&': 'AMP', '\\': 'BACKSLASH',
        '|': 'BAR', '<': 'LT', '>': 'GT', '=': 'EQ', '!': 'BANG',
        '.': 'DOT', ':': 'COLON', '?': 'QUESTION', '#': 'HASH',
        '"': 'QUOTE', "'": 'APOST', '~': 'TILDE', '@': 'AT',
        '_': 'UNDER',
    }
    if ch in names:
        return names[ch]
    if ch.isalnum():
        return ch.upper()
    return f"U{ord(ch):04X}"


def _get_single_op_ignores(ch, ascii_glyphs):
    """Generate ignore rules for a single-char operator to avoid conflicts with multi-char ops."""
    g = lambda c: ascii_glyphs.get(c)
    ignores = []

    # Check which multi-char ops contain this char
    for op in MULTI_OPS:
        if ch not in op:
            continue
        idx = op.index(ch)
        # If our char is at position idx, we need to check context
        op_glyphs = [g(c) for c in op]
        if not all(op_glyphs):
            continue

        base = g(ch)
        if idx == 0 and len(op) > 1:
            # Our char is first: ignore if followed by rest
            rest = [g(c) for c in op[1:]]
            ignores.append(f"ignore sub {base}' {' '.join(rest)};")
        elif idx == len(op) - 1:
            # Our char is last: ignore if preceded by earlier chars
            pre = [g(c) for c in op[:idx]]
            ignores.append(f"ignore sub {' '.join(pre)} {base}';")
        else:
            # Our char is in the middle
            pre = [g(c) for c in op[:idx]]
            post = [g(c) for c in op[idx+1:]]
            ignores.append(f"ignore sub {' '.join(pre)} {base}' {' '.join(post)};")

    # Deduplicate
    return list(dict.fromkeys(ignores))


def update_name_table(font, family_name="RocMono"):
    """Update the font's name table."""
    name_table = font["name"]

    # Name IDs: 1=Family, 2=Subfamily, 4=Full, 6=PostScript
    for record in name_table.names:
        if record.nameID == 1:
            record.string = family_name
        elif record.nameID == 2:
            record.string = "Regular"
        elif record.nameID == 4:
            record.string = f"{family_name} Regular"
        elif record.nameID == 6:
            record.string = f"{family_name}-Regular"


def build_font(input_path, output_path, family_name="RocMono"):
    """Main pipeline: load font, add alternates, build tables, save."""
    print(f"Loading {input_path}...")
    font = TTFont(input_path)

    print("Analyzing font glyphs...")
    ascii_glyphs = get_all_ascii_glyph_names(font)
    print(f"  Found {len(ascii_glyphs)} ASCII glyphs")

    print("Creating alternate glyphs...")
    alternates = create_alternate_glyphs(font, ascii_glyphs)
    total_alts = sum(len(v) for v in alternates.values())
    print(f"  Created {total_alts} alternate glyphs")

    print("Building CPAL (color palettes)...")
    build_cpal(font)

    print("Building COLR (color layers)...")
    build_colr(font, ascii_glyphs, alternates)

    print("Generating OpenType feature code...")
    fea_code = generate_feature_code(font, ascii_glyphs, alternates)

    # Write feature code to temp file for debugging
    fea_path = Path(output_path).with_suffix(".fea")
    fea_path.write_text(fea_code)
    print(f"  Feature code written to {fea_path}")

    print("Compiling OpenType features...")
    addOpenTypeFeatures(font, fea_path)

    print("Updating font names...")
    update_name_table(font, family_name)

    # Determine output format
    out = Path(output_path)
    if out.suffix == ".woff2":
        font.flavor = "woff2"
    elif out.suffix == ".woff":
        font.flavor = "woff"

    print(f"Saving {output_path}...")
    font.save(str(output_path))
    print(f"Done! Output: {output_path}")

    # Cleanup temp fea file
    # fea_path.unlink()  # Keep for debugging

    # Print stats
    print(f"\nFont statistics:")
    print(f"  Total glyphs: {len(font.getGlyphOrder())}")
    print(f"  Palettes: {len(PALETTES)}")
    print(f"  Keywords: {len(KEYWORDS)}")
    print(f"  Multi-char operators: {len(MULTI_OPS)}")
    print(f"  Single-char operators: {len(SINGLE_OPS)}")


def main():
    parser = argparse.ArgumentParser(
        description="Build a syntax-highlighting font for Roc"
    )
    parser.add_argument(
        "input",
        help="Input font file (TTF or OTF)"
    )
    parser.add_argument(
        "-o", "--output",
        default="RocMono.woff2",
        help="Output font file (default: RocMono.woff2)"
    )
    parser.add_argument(
        "--name",
        default="RocMono",
        help="Font family name (default: RocMono)"
    )
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    build_font(args.input, args.output, args.name)


if __name__ == "__main__":
    main()
