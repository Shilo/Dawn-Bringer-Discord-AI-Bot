#!/usr/bin/env python3
"""
Discord Embed Endpoint Testing

Tests Discord preview image generation endpoints for deployed applications.
Supports both HTTP endpoint testing (production) and local generation testing.

Can test specific share links, URLs, or generate images locally with OCR analysis
to verify proper Discord embed rendering.

Usage:
  From project root: python test/test_discord_embed_endpoint.py <share_id_or_url>
  From test directory: python test_discord_embed_endpoint.py <share_id_or_url>

Examples:
  python test/test_discord_embed_endpoint.py dTn5RP
  python test/test_discord_embed_endpoint.py https://my-app.railway.app/Hxps8U
"""

import sys
import os
import subprocess
import tempfile
from pathlib import Path

# Add project root to Python path so we can import modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def analyze_image_content(image_data, expected_text=None):
    """
    Analyze image content to verify rendering quality and detect issues.

    Args:
        image_data: PNG image bytes
        expected_text: Expected text content (optional)

    Returns:
        dict: Analysis results with quality metrics
    """
    from PIL import Image
    import io

    results = {
        'image_size': len(image_data),
        'dimensions': None,
        'text_pixels': 0,
        'background_pixels': 0,
        'text_density': 0.0,
        'empty_box_score': 0,
        'render_quality': 'unknown',
        'content_verification': 'unknown'
    }

    try:
        img = Image.open(io.BytesIO(image_data))
        # Use getdata() for now, will be updated when Pillow 14 is released
        pixels = list(img.getdata())

        width, height = img.size
        results['dimensions'] = (width, height)

        # Handle different pixel formats (RGB tuples, palette indices, etc.)
        def is_text_pixel(pixel):
            if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                # RGB/RGBA format - check if it's white/light colored
                r, g, b = pixel[0], pixel[1], pixel[2]
                # More lenient white detection
                return r > 200 and g > 200 and b > 200  # Light colored text
            elif isinstance(pixel, int):
                # Palette mode - assume white is high values
                return pixel > 200
            else:
                return False

        def is_bg_pixel(pixel):
            if isinstance(pixel, (tuple, list)) and len(pixel) >= 3:
                # RGB/RGBA format - check if it matches Discord background (more lenient)
                r, g, b = pixel[0], pixel[1], pixel[2]
                return abs(r - 54) < 20 and abs(g - 57) < 20 and abs(b - 63) < 20
            elif isinstance(pixel, int):
                # Palette mode - background is typically low values
                return pixel < 100
            else:
                return False


        results['text_pixels'] = sum(1 for pixel in pixels if is_text_pixel(pixel))
        results['background_pixels'] = sum(1 for pixel in pixels if is_bg_pixel(pixel))
        results['text_density'] = results['text_pixels'] / len(pixels) if pixels else 0

        # Check for empty character boxes (less aggressive detection)
        empty_box_count = 0

        # Only scan in the main text area (top portion where text should be, more focused)
        text_area_width = min(600, width - 40)  # Focus on left side
        text_area_height = min(200, height - 40)  # Focus on top portion

        # Sample less frequently to avoid false positives
        for y in range(20, text_area_height, 40):  # Less frequent vertical sampling
            for x in range(20, text_area_width, 25):  # Less frequent horizontal sampling
                char_width, char_height = 15, 25
                if x + char_width >= text_area_width or y + char_height >= text_area_height:
                    continue

                bg_pixels_in_box = 0
                total_pixels_in_box = 0

                for dy in range(char_height):
                    for dx in range(char_width):
                        pixel_idx = (y + dy) * width + (x + dx)
                        if pixel_idx < len(pixels):
                            if is_bg_pixel(pixels[pixel_idx]):
                                bg_pixels_in_box += 1
                            total_pixels_in_box += 1

                # More lenient threshold: >98% background to count as empty box
                if total_pixels_in_box > 250 and (bg_pixels_in_box / total_pixels_in_box) > 0.98:
                    empty_box_count += 1

        results['empty_box_score'] = empty_box_count

        # Determine render quality (more realistic thresholds for Discord previews)
        if results['text_pixels'] < 500:
            results['render_quality'] = 'poor'
            results['content_verification'] = 'no_text_detected'
        elif results['empty_box_score'] > 100:
            results['render_quality'] = 'poor'
            results['content_verification'] = 'too_many_empty_boxes'
        elif results['text_pixels'] > 5000 and results['text_density'] > 0.01:
            results['render_quality'] = 'good'
            results['content_verification'] = 'text_rendered_properly'
        elif results['text_pixels'] > 1000:
            results['render_quality'] = 'fair'
            results['content_verification'] = 'text_rendered_adequately'
        else:
            results['render_quality'] = 'poor'
            results['content_verification'] = 'minimal_text'

        # Basic content verification for expected text
        if expected_text:
            # Use the image generator's sanitization (which includes star conversion)
            from preview_image_generator import PreviewImageGenerator
            gen = PreviewImageGenerator()
            sanitized_expected = gen.sanitize_text(expected_text)

            # Count all star-like characters in original
            expected_stars = sum(1 for char in expected_text if ord(char) in [9733, 9734, 11088, 10032, 10033, 9735])
            actual_asterisks = sanitized_expected.count('*')

            results['asterisks_in_image'] = actual_asterisks
            results['expected_lower'] = sanitized_expected.lower()

            if expected_stars > 0:
                if actual_asterisks >= expected_stars:
                    results['star_conversion'] = 'successful'
                else:
                    results['star_conversion'] = 'failed'
            else:
                results['star_conversion'] = 'not_applicable'

    except Exception as e:
        results['render_quality'] = 'error'
        results['content_verification'] = f'analysis_failed: {e}'

    return results

def verify_content_match(expected_text):
    """
    Verify that expected content characteristics are present in the rendered output.

    Args:
        expected_text: Expected text content

    Returns:
        dict: Content verification results
    """
    from web_server import sanitize_text_for_preview

    # Count all star-like characters using Unicode code points
    star_count = sum(1 for char in expected_text if ord(char) in [9733, 9734, 11088, 10032, 10033, 9735])

    results = {
        'text_length': len(expected_text),
        'sanitized_length': 0,
        'star_count': star_count,
        'asterisk_count': 0,
        'content_verification': 'unknown'
    }

    # Check sanitization
    sanitized = sanitize_text_for_preview(expected_text)
    results['sanitized_length'] = len(sanitized)
    results['asterisk_count'] = sanitized.count('*')

    # Verify star conversion
    if results['star_count'] > 0:
        if results['asterisk_count'] >= results['star_count']:
            results['content_verification'] = 'stars_converted_properly'
        else:
            results['content_verification'] = 'star_conversion_incomplete'
    else:
        results['content_verification'] = 'no_stars_to_convert'

    return results

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

            # Perform OCR analysis on the downloaded image
            print("[OCR] Analyzing image content...")
            ocr_results = analyze_image_content(response.content, None)  # No expected text for HTTP responses

            print(f"[OCR] Text pixels: {ocr_results['text_pixels']}")
            print(f"[OCR] Text density: {ocr_results['text_density']:.4f}")
            print(f"[OCR] Empty box score: {ocr_results['empty_box_score']}")
            print(f"[OCR] Render quality: {ocr_results['render_quality']}")
            print(f"[OCR] Content verification: {ocr_results['content_verification']}")

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
        from web_server import sanitize_text_for_preview

        # Get share data
        share = share_db.get_share(share_id)
        if not share:
            print(f"[ERROR] Share not found in database: {share_id}")
            return False

        # Sanitize text for image generation (same as production)
        sanitized_question = sanitize_text_for_preview(share['prompt'])
        sanitized_answer = sanitize_text_for_preview(share['response'])

        # Handle potential Unicode issues in console output
        try:
            # Safely truncate strings, avoiding Unicode issues
            prompt_str = str(sanitized_question)
            response_str = str(sanitized_answer)

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
            question=sanitized_question,
            answer=sanitized_answer,
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

        # Perform OCR analysis and content verification
        print("[OCR] Analyzing image content and verifying rendering...")
        expected_text = share['response']  # Use the actual response text for comparison
        ocr_results = analyze_image_content(image_data, expected_text)

        print(f"[OCR] Text pixels: {ocr_results['text_pixels']}")
        print(f"[OCR] Text density: {ocr_results['text_density']:.4f}")
        print(f"[OCR] Empty box score: {ocr_results['empty_box_score']}")
        print(f"[OCR] Render quality: {ocr_results['render_quality']}")
        print(f"[OCR] Content verification: {ocr_results['content_verification']}")

        if 'star_conversion' in ocr_results:
            print(f"[OCR] Star conversion: {ocr_results['star_conversion']}")

        # Additional content verification using the image generator's sanitization
        from preview_image_generator import PreviewImageGenerator
        generator = PreviewImageGenerator()
        image_sanitized = generator.sanitize_text(expected_text)

        content_check = {
            'original_length': len(expected_text),
            'image_sanitized_length': len(image_sanitized),
            'stars_in_original': expected_text.count('★'),
            'asterisks_in_image': image_sanitized.count('*'),
            'content_verification': 'checking_star_conversion'
        }

        if content_check['stars_in_original'] > 0:
            if content_check['asterisks_in_image'] >= content_check['stars_in_original']:
                content_check['content_verification'] = 'stars_converted_properly'
            else:
                content_check['content_verification'] = 'star_conversion_incomplete'
        else:
            content_check['content_verification'] = 'no_stars_to_convert'

        print(f"[OCR] Original text length: {content_check['original_length']}")
        print(f"[OCR] Image-sanitized text length: {content_check['image_sanitized_length']}")
        print(f"[OCR] Stars in original: {content_check['stars_in_original']}")
        print(f"[OCR] Asterisks in image text: {content_check['asterisks_in_image']}")
        print(f"[OCR] Content verification: {content_check['content_verification']}")

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

    print("Discord Embed Endpoint Test")
    print("=" * 55)
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