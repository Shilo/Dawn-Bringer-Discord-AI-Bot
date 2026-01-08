# Discord Preview Image Test Script

This script allows you to test the Discord preview image generation for shared conversations.

## Usage

```bash
# From the project root directory:
# Test a specific share ID or full URL (works with or without running server)
python test/test_preview_endpoint.py <share_id_or_url>

# Show help and list recent shares
python test/test_preview_endpoint.py

# Or from the test directory:
# Test a specific share ID or URL
python test_preview_endpoint.py <share_id_or_url>
```

## Examples

```bash
# Test with share ID only (uses localhost:8000)
python test/test_preview_endpoint.py dTn5RP

# Test with full URL (share ID extracted automatically)
python test/test_preview_endpoint.py http://localhost:8000/QyZiNQ

# Test with preview URL (share ID extracted automatically)
python test/test_preview_endpoint.py https://my-app.railway.app/api/preview/abc123.png

# List recent shares and get help (from project root)
python test/test_preview_endpoint.py

# Same commands work from test directory
cd test
python test_preview_endpoint.py QyZiNQ
python test_preview_endpoint.py http://localhost:8000/QyZiNQ
```

## How It Works

The script tests the preview image generation in two ways:

1. **HTTP Request**: Tries to fetch the image from `/api/preview/{share_id}.png`
2. **Direct Generation**: If HTTP fails, generates the image directly from the database

## Arguments

The script accepts either:
- **Share ID**: 6-character alphanumeric string (e.g., `dTn5RP`)
- **Full URL**: Complete URL containing the share ID (e.g., `http://localhost:8000/QyZiNQ`)
- **Preview URL**: Direct preview endpoint URL (e.g., `https://my-app.railway.app/api/preview/abc123.png`)

## Features

- ✅ **Smart URL Parsing**: Automatically extracts share ID from URLs
- ✅ **Flexible Input**: Accepts share IDs, full URLs, or preview URLs
- ✅ **HTTP Testing**: Tests actual web endpoint when server is running
- ✅ **Fallback Mode**: Generates images directly from database when HTTP fails
- ✅ **Image Saving**: Saves generated images to temp directory for inspection
- ✅ **Auto-Opening**: Automatically opens images in default viewer
- ✅ **Detailed Output**: Shows response headers, status codes, and file sizes
- ✅ **Share Discovery**: Lists recent shares for testing reference

## Output Example

```
Discord Preview Image Test
==================================================
Share ID: dTn5RP
Base URL: http://localhost:8000

[INFO] Testing preview endpoint: http://localhost:8000/api/preview/dTn5RP.png
[ERROR] HTTP request failed: [connection error]
Falling back to direct database testing...
[INFO] Testing image generation directly for share: dTn5RP
[INFO] Found share - Prompt: What are the main challenges...
[INFO] Found share - Response: The main challenges include...
[SUCCESS] Image generated successfully! Size: 46524 bytes
[SAVE] Image saved to: C:\Temp\discord_preview_dTn5RP_direct.png
[OPEN] Image opened in default viewer

[SUCCESS] Test completed successfully!
```

## Requirements

- Python 3.8+
- Access to the project database (shares.db)
- PIL/Pillow (for image generation)
- requests (optional, for HTTP testing)

## Cross-Platform Support

The script automatically detects your platform and uses the appropriate method to open images:

- **Windows**: `os.startfile()`
- **macOS**: `open` command
- **Linux**: `xdg-open` command