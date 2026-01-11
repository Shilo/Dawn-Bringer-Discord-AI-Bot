# Discord Preview Testing Suite

This directory contains comprehensive testing tools for Discord preview image generation and embedding functionality.

## Test Files

### `test_discord_embed_rendering.py`
**Purpose:** Batch quality assurance testing for Discord embed image rendering

**Usage:**
```bash
python test/discord_preview/test_discord_embed_rendering.py
```

**What it does:**
- Tests multiple predefined text scenarios
- Verifies font fallback functionality
- Checks star/emoji conversion
- Saves test images for manual inspection
- Reports comprehensive quality metrics

### `test_discord_embed_endpoint.py`
**Purpose:** HTTP endpoint testing for deployed Discord embed services

**Usage:**
```bash
# Test a specific share ID or full URL
python test/discord_preview/test_discord_embed_endpoint.py <share_id_or_url>

# Show help and list recent shares
python test/discord_preview/test_discord_embed_endpoint.py
```

**Examples:**
```bash
# Test with share ID only (uses localhost:8000)
python test/discord_preview/test_discord_embed_endpoint.py dTn5RP

# Test with full URL (share ID extracted automatically)
python test/discord_preview/test_discord_embed_endpoint.py http://localhost:8000/QyZiNQ

# Test with preview URL (share ID extracted automatically)
python test/discord_preview/test_discord_embed_endpoint.py https://my-app.railway.app/api/preview/abc123.png

# List recent shares and get help
python test/discord_preview/test_discord_embed_endpoint.py
```

### `test_discord_preview_ocr.py`
**Purpose:** Interactive OCR testing with custom input strings

**Usage:**
```bash
# Test custom strings with OCR analysis
python test/discord_preview/test_discord_preview_ocr.py "your test string"

# Built-in star tests
python test/discord_preview/test_discord_preview_ocr.py --test-star
python test/discord_preview/test_discord_preview_ocr.py --test-emoji
```

**Examples:**
```bash
# Test star characters
python test/discord_preview/test_discord_preview_ocr.py "★★★★★ Perfect!"

# Test emoji conversion
python test/discord_preview/test_discord_preview_ocr.py "⭐⭐⭐⭐⭐ Amazing!"

# Test mixed content
python test/discord_preview/test_discord_preview_ocr.py "Rating: ★★★★☆"
```

## How Each Tool Works

### Rendering Test (`test_discord_embed_rendering.py`)
- **Batch Testing**: Tests multiple predefined scenarios automatically
- **Quality Assurance**: Verifies font fallback and character rendering
- **File Generation**: Creates `test_render_*.png` files for manual inspection
- **Comprehensive Analysis**: OCR analysis of all generated images

### Endpoint Test (`test_discord_embed_endpoint.py`)
- **HTTP Testing**: Tests actual web endpoints when server is running
- **Direct Generation**: Falls back to database generation when HTTP fails
- **URL Parsing**: Automatically extracts share IDs from various URL formats
- **Production Verification**: Tests deployed Railway applications

### OCR Test (`test_discord_preview_ocr.py`)
- **Interactive Testing**: Test any custom string input
- **Real-time Analysis**: OCR analysis of generated images
- **Font Verification**: Confirms proper font fallback for special characters
- **Star Conversion**: Validates ⭐→★ emoji conversion

## Common Arguments

All tools accept:
- **Share IDs**: 6-character alphanumeric strings (e.g., `dTn5RP`)
- **Full URLs**: Complete URLs containing share IDs
- **Preview URLs**: Direct `/api/preview/` endpoint URLs

## Features

- ✅ **Font Fallback**: Automatic selection of appropriate fonts for each character
- ✅ **Star Conversion**: ⭐ emojis converted to ★ symbols for consistent rendering
- ✅ **OCR Analysis**: Pixel-level analysis of rendered images
- ✅ **Quality Metrics**: Text density, empty box detection, render quality scores
- ✅ **Cross-Platform**: Works on Windows, Linux (Railway), and macOS
- ✅ **Auto-Opening**: Generated images open in default system viewer

## Output Examples

### Rendering Test (Batch Analysis)
```bash
[DISCORD EMBED] Image Rendering Quality Analysis
=======================================================

[TEST 1] Star rating text
Text font:   C:\WINDOWS\fonts\arial.ttf
Symbol font: C:\WINDOWS\fonts\seguisym.ttf
Emoji font:  C:\WINDOWS\fonts\seguiemj.ttf
   Size: 12484 bytes
   Text pixels: 5083
   Quality: good
   ✅ Stars properly preserved/converted
   Saved: test_render_1.png
```

### Endpoint Test (HTTP/Direct Generation)
```bash
Discord Embed Endpoint Test
=======================================================
Input: dTn5RP
Parsed Share ID: dTn5RP
Base URL: http://localhost:8000

[INFO] Testing preview endpoint: http://localhost:8000/api/preview/dTn5RP.png
[ERROR] HTTP request failed: [connection error]
Falling back to direct database testing...
[INFO] Testing image generation directly for share: dTn5RP
[SUCCESS] Image generated successfully! Size: 46524 bytes
[SAVE] Image saved to: C:\Temp\discord_preview_dTn5RP_direct.png
[OPEN] Image opened in default viewer
[OCR] Text pixels: 12345
[OCR] Render quality: good

[SUCCESS] Test completed successfully!
```

### OCR Test (Interactive Analysis)
```bash
String Rendering & OCR Test
============================================================
Input string: '★★★★★ Perfect!'
[SUCCESS] Image generated successfully! Size: 10350 bytes
[SAVE] Image saved: C:\Temp\string_test_12345.png
[OPEN] Image opened in default viewer
[OCR] Text pixels: 4276
[OCR] Render quality: good
[SUCCESS] Star rendering - 5 stars preserved and rendered
PASS: String rendering and OCR working correctly!
```

## Requirements

- Python 3.8+
- PIL/Pillow (for image generation and analysis)
- Database access (for endpoint testing with real shares)
- requests (optional, for HTTP endpoint testing)

## Cross-Platform Support

All tools automatically detect your platform and use appropriate methods:

- **Font Loading**: Windows (C:\Windows\Fonts), Linux (/usr/share/fonts), macOS (system fonts)
- **Image Opening**: Windows (`os.startfile()`), macOS (`open`), Linux (`xdg-open`)
- **HTTP Testing**: Works on all platforms with requests library

## File Organization

```
test/discord_preview/
├── README.md                           # This documentation
├── test_discord_embed_rendering.py     # Batch quality testing
├── test_discord_embed_endpoint.py      # HTTP endpoint testing
└── test_discord_preview_ocr.py         # Interactive OCR testing
```

## Troubleshooting

### "Font not found" errors
- Install system fonts or ensure font directories are accessible
- Tools will gracefully fall back to available fonts

### "Connection refused" errors
- Ensure the web server is running for HTTP testing
- Tools automatically fall back to direct database generation

### Unicode display issues
- Expected on Windows console - images render correctly regardless
- Use built-in tests (`--test-star`, `--test-emoji`) for reliable testing