#!/usr/bin/env python3
"""
Test script for Discord preview image endpoint.

This script allows you to test the preview image generation for a specific share link.
Can be run from project root or test directory.

Usage:
  From project root: python test/test_preview_endpoint.py <share_id>
  From test directory: python test_preview_endpoint.py <share_id>

Example: python test_preview_endpoint.py dTn5RP
"""

import sys
import os
import subprocess
import tempfile
from pathlib import Path

# Add project root to Python path so we can import modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def extract_share_id(input_str: str) -> tuple[str, str]:
    """Extract share ID and base URL from input string.

    Args:
        input_str: Either a share ID (6 chars) or a full URL

    Returns:
        Tuple of (share_id, base_url)
    """
    import re
    from urllib.parse import urlparse

    # Check if it's a full URL
    if '://' in input_str:
        parsed = urlparse(input_str)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        path_parts = parsed.path.strip('/').split('/')

        # Handle preview endpoint URLs (e.g., /api/preview/dTn5RP.png)
        if 'preview' in path_parts:
            preview_index = path_parts.index('preview')
            if preview_index + 1 < len(path_parts):
                next_part = path_parts[preview_index + 1]
                # Remove .png extension if present
                share_id = next_part.replace('.png', '')
                if re.match(r'^[a-zA-Z0-9]{6}$', share_id):
                    return share_id, base_url

        # Look for share ID in any path part
        for part in path_parts:
            # Remove .png extension if present
            clean_part = part.replace('.png', '')
            if re.match(r'^[a-zA-Z0-9]{6}$', clean_part):
                return clean_part, base_url

        # If no share ID found in path, assume the last part (without extension) is the ID
        if path_parts:
            last_part = path_parts[-1].replace('.png', '')
            if re.match(r'^[a-zA-Z0-9]{6}$', last_part):
                return last_part, base_url

        print(f"[ERROR] Could not find valid share ID in URL: {input_str}")
        return None, None
    else:
        # Assume it's just a share ID
        if re.match(r'^[a-zA-Z0-9]{6}$', input_str):
            return input_str, "http://localhost:8000"
        else:
            print(f"[ERROR] Invalid share ID format: {input_str}")
            print("Share ID must be exactly 6 alphanumeric characters")
            return None, None

def test_preview_endpoint(share_id: str, base_url: str = "http://localhost:8000"):
    """Test the preview image endpoint for a given share ID.

    Args:
        share_id: The share ID to test (e.g., 'dTn5RP')
        base_url: Base URL of the server (default: localhost:8000)
    """
    # Validate share ID format
    import re
    if not re.match(r'^[a-zA-Z0-9]{6}$', share_id):
        print(f"[ERROR] Invalid share ID format: {share_id}")
        print("Share ID must be exactly 6 alphanumeric characters")
        return False

    # Try to test via HTTP request first
    try:
        import requests
        preview_url = f"{base_url}/api/preview/{share_id}.png"
        print(f"[INFO] Testing preview endpoint: {preview_url}")

        response = requests.get(preview_url, timeout=10)

        if response.status_code == 200:
            print(f"[SUCCESS] HTTP request successful! Status: {response.status_code}")

            # Get response headers
            content_type = response.headers.get('content-type', 'unknown')
            content_length = response.headers.get('content-length', 'unknown')
            image_source = response.headers.get('x-image-source', 'unknown')

            print(f"   Content-Type: {content_type}")
            print(f"   Content-Length: {content_length} bytes")
            print(f"   Image Source: {image_source}")

            # Save the image to a temporary file
            temp_dir = Path(tempfile.gettempdir())
            image_filename = f"discord_preview_{share_id}.png"
            image_path = temp_dir / image_filename

            with open(image_path, 'wb') as f:
                f.write(response.content)

            print(f"[SAVE] Image saved to: {image_path}")
            print(f"[INFO] Image size: {len(response.content)} bytes")

            # Try to open the image
            open_image(image_path)
            return True

        elif response.status_code == 404:
            print(f"[ERROR] Share not found via HTTP: {share_id}")
            print("Falling back to direct database testing...")
        else:
            print(f"[ERROR] HTTP request failed: HTTP {response.status_code}")
            print("Falling back to direct database testing...")

    except ImportError:
        print("[INFO] Requests library not available, skipping HTTP test")
    except Exception as e:
        print(f"[ERROR] HTTP request failed: {e}")
        print("Falling back to direct database testing...")

    # Fallback: Test directly by generating the image
    print(f"[INFO] Testing image generation directly for share: {share_id}")

    try:
        import share_db
        from preview_image_generator import generate_conversation_preview

        # Get share data
        share = share_db.get_share(share_id)
        if not share:
            print(f"[ERROR] Share not found in database: {share_id}")
            return False

        # Handle potential Unicode issues in console output
        try:
            # Safely truncate strings, avoiding Unicode issues
            prompt_str = str(share['prompt'])
            response_str = str(share['response'])

            # Use ASCII-safe preview
            prompt_preview = prompt_str.encode('ascii', 'replace').decode('ascii')[:50]
            response_preview = response_str.encode('ascii', 'replace').decode('ascii')[:50]
        except Exception:
            prompt_preview = "Content preview unavailable"
            response_preview = "Content preview unavailable"

        print(f"[INFO] Found share - Prompt: {prompt_preview}...")
        print(f"[INFO] Found share - Response: {response_preview}...")

        # Generate preview image
        image_data = generate_conversation_preview(
            question=share['prompt'],
            answer=share['response'],
            bot_name="Dawn Bringer"
        )

        print(f"[SUCCESS] Image generated successfully! Size: {len(image_data)} bytes")

        # Save the image to a temporary file
        temp_dir = Path(tempfile.gettempdir())
        image_filename = f"discord_preview_{share_id}_direct.png"
        image_path = temp_dir / image_filename

        with open(image_path, 'wb') as f:
            f.write(image_data)

        print(f"[SAVE] Image saved to: {image_path}")

        # Try to open the image
        open_image(image_path)

        return True

    except Exception as e:
        print(f"[ERROR] Direct testing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def open_image(image_path: Path):
    """Open the image file using the system's default image viewer.

    Args:
        image_path: Path to the image file
    """
    try:
        if sys.platform == "win32":
            # Windows
            os.startfile(str(image_path))
        elif sys.platform == "darwin":
            # macOS
            subprocess.run(["open", str(image_path)], check=True)
        else:
            # Linux/Unix
            subprocess.run(["xdg-open", str(image_path)], check=True)

        print(f"[OPEN] Image opened in default viewer")
    except Exception as e:
        print(f"[WARNING] Could not open image automatically: {e}")
        print(f"   You can manually open: {image_path}")

def list_recent_shares(base_url: str = "http://localhost:8000", limit: int = 10):
    """List recent shares for testing.

    Args:
        base_url: Base URL of the server
        limit: Maximum number of shares to list
    """
    print("[INFO] Fetching recent shares for testing...")
    print("Note: This requires direct database access, so it only works locally")

    try:
        import share_db
        conn = share_db.get_db_connection()

        cursor = conn.execute("""
            SELECT id, created_at, view_count
            FROM shares
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("[ERROR] No shares found in database")
            return

        print(f"\nRecent shares (last {len(rows)}):")
        print("-" * 50)
        for row in rows:
            share_id, created_at, view_count = row
            print(f"  {share_id} - {created_at} - {view_count} views")

        print("\nTo test a share, run:")
        print("   python test/test_preview_endpoint.py <share_id>")
        print("   (or from test directory: python test_preview_endpoint.py <share_id>)")
        print("\nExample:")
        print(f"   python test/test_preview_endpoint.py {rows[0][0]}")

    except Exception as e:
        print(f"[ERROR] Could not fetch shares: {e}")
        print("Make sure you're running this from the project directory")

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Discord Preview Image Test Script")
        print("=" * 50)
        print("Usage:")
        print("  From project root: python test/test_preview_endpoint.py <share_id_or_url>")
        print("  From test directory: python test_preview_endpoint.py <share_id_or_url>")
        print()
        print("Arguments:")
        print("  share_id_or_url - Either:")
        print("    - 6-character alphanumeric share ID (e.g., dTn5RP)")
        print("    - Full URL (e.g., http://localhost:8000/QyZiNQ)")
        print("    - Preview URL (e.g., http://localhost:8000/api/preview/QyZiNQ.png)")
        print()
        print("Examples:")
        print("  python test/test_preview_endpoint.py dTn5RP")
        print("  python test/test_preview_endpoint.py http://localhost:8000/QyZiNQ")
        print("  python test/test_preview_endpoint.py https://my-app.railway.app/api/preview/abc123.png")
        print("  cd test && python test_preview_endpoint.py QyZiNQ")
        print("  cd test && python test_preview_endpoint.py http://localhost:8000/QyZiNQ")
        print()

        # Try to list recent shares
        list_recent_shares()
        return

    input_arg = sys.argv[1]

    # Extract share ID and base URL from input
    share_id, base_url = extract_share_id(input_arg)

    if share_id is None:
        print("\n[ERROR] Could not parse share ID from input!")
        sys.exit(1)

    print("Discord Preview Image Test")
    print("=" * 50)
    print(f"Input: {input_arg}")
    print(f"Parsed Share ID: {share_id}")
    print(f"Base URL: {base_url}")
    print()

    success = test_preview_endpoint(share_id, base_url)

    if success:
        print("\n[SUCCESS] Test completed successfully!")
    else:
        print("\n[ERROR] Test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()