# Discord Preview Image Test Script

This script allows you to test the Discord preview image generation for shared conversations.

## Usage

```bash
# From the project root directory:
# Test a specific share ID (works with or without running server)
python test/test_preview_endpoint.py <share_id> [base_url]

# Show help and list recent shares
python test/test_preview_endpoint.py

# Or from the test directory:
# Test a specific share ID
python test_preview_endpoint.py <share_id> [base_url]
```

## Examples

```bash
# Test local share with default server (from project root)
python test/test_preview_endpoint.py dTn5RP

# Test with custom server URL (from project root)
python test/test_preview_endpoint.py abc123 https://my-app.railway.app

# List recent shares and get help (from project root)
python test/test_preview_endpoint.py

# Same commands work from test directory
cd test
python test_preview_endpoint.py dTn5RP
```

## How It Works

The script tests the preview image generation in two ways:

1. **HTTP Request**: Tries to fetch the image from `/api/preview/{share_id}.png`
2. **Direct Generation**: If HTTP fails, generates the image directly from the database

## Features

- ✅ Validates share ID format (6 alphanumeric characters)
- ✅ Tests HTTP endpoint when server is running
- ✅ Falls back to direct database testing
- ✅ Saves generated images to temp directory
- ✅ Automatically opens images in default viewer
- ✅ Shows detailed response information
- ✅ Lists recent shares for testing

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