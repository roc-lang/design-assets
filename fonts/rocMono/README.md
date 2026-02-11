# Roc Syntax Highlighting Font

A Python script that takes any monospace font and produces a version with built-in syntax highlighting for Roc, using OpenType COLRv0 colored glyphs and `calt` contextual alternates.

Based on the technique described in [Font with Built-in Syntax Highlighting](https://blog.glyphdrawing.club/font-with-built-in-syntax-highlighting/).

## How It Works

The font embeds syntax highlighting rules directly in its OpenType substitution tables — no JavaScript or editor plugins needed. When text is rendered, the font's `calt` (contextual alternates) feature pattern-matches keywords, operators, comments, strings, types, and numbers, substituting them with colored glyph variants via COLRv0 color layers.

Two color palettes are included (light and dark), switchable via CSS `@font-palette-values`.

## What Gets Highlighted

| Category | Light Color | Dark Color | Examples |
|----------|------------|------------|---------|
| Keywords | `#0000ff` | `#c678dd` | `if`, `else`, `match`, `for`, `while`, `return`, `import` |
| Operators | `#800080` | `#56b6c2` | `->`, `=>`, `\|>`, `==`, `!=`, `+`, `-`, `*` |
| Comments | `#008000` | `#5c6370` | `# everything after hash` |
| Types | `#c18401` | `#e5c07b` | `Str`, `I64`, `List`, `Bool`, `Ok`, `Err` |
| Strings | `#008000` | `#98c379` | `"text inside quotes"` |
| Numbers | `#ff8c00` | `#d19a66` | `42`, `0xFF`, `3.14` |

## Quick Start

```bash
cd fonts/

# Set up a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install "fonttools[woff]"

# Download a base font (e.g. Iosevka, SIL OFL licensed)
curl -LO https://github.com/be5invis/Iosevka/releases/download/v33.2.1/PkgTTF-Iosevka-33.2.1.zip
unzip PkgTTF-Iosevka-33.2.1.zip -d iosevka

# Build the font
python build_roc_font.py iosevka/Iosevka-Regular.ttf -o RocMono.woff2
```

## Usage

```css
@font-face {
  font-family: 'RocMono';
  src: url('RocMono.woff2') format('woff2');
}

pre, code {
  font-family: 'RocMono', monospace;
}

/* Dark theme */
@font-palette-values --roc-dark {
  font-family: 'RocMono';
  base-palette: 1;
}

@media (prefers-color-scheme: dark) {
  pre, code { font-palette: --roc-dark; }
}
```

## CLI Options

```
python build_roc_font.py INPUT [-o OUTPUT] [--name NAME]

positional arguments:
  INPUT                 Input font file (TTF or OTF)

options:
  -o, --output OUTPUT   Output font file (default: RocMono.woff2)
  --name NAME           Font family name (default: RocMono)
```

## Testing

Open `test_roc_font.html` in a browser with the generated `RocMono.woff2` in the same directory. The page includes test sections for each syntax category and a light/dark theme toggle.

## Known Limitations

- **No multi-line strings** — `\\` multiline strings won't highlight across lines
- **String interpolation** — `${expr}` inside strings won't un-color back to expression colors
- **Comment in strings** — `#` inside a string on the same line will start comment coloring
- **No semantic analysis** — can't distinguish type annotations from tag names (both uppercase)

These limitations are inherent to the OpenType font approach and are acceptable for documentation use.

## Keywords

The 34 keywords are synced from the [Roc tokenizer](https://github.com/roc-lang/roc/blob/main/src/parse/tokenize.zig) (lines 372-407):

`implements`, `generates`, `interface`, `exposing`, `packages`, `platform`, `provides`, `requires`, `exposes`, `imports`, `targets`, `expect`, `hosted`, `import`, `module`, `return`, `break`, `crash`, `match`, `where`, `while`, `else`, `with`, `app`, `dbg`, `for`, `has`, `var`, `and`, `as`, `if`, `in`, `or`, `package`
