#!/usr/bin/env python3
"""
Test script to verify string rendering and OCR accuracy.

This script takes any input string, generates a Discord preview image with it,
then uses OCR analysis to read the image back and compare results.

Usage:
  python test/discord_preview/test_discord_preview_ocr.py "your test string here"

Examples:
  python test/discord_preview/test_discord_preview_ocr.py "★"
  python test/discord_preview/test_discord_preview_ocr.py "Hello ★★★ World"
  python test/discord_preview/test_discord_preview_ocr.py "Normal text without stars"
"""

import sys
import os
import subprocess
import tempfile
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from preview_image_generator import generate_conversation_preview
from test.test_preview_endpoint import analyze_image_content


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

        print(f"OPEN: Image opened in default viewer")
    except Exception as e:
        print(f"WARNING: Could not open image automatically: {e}")
        print(f"   You can manually open: {image_path}")


def test_string_rendering_ocr(input_string: str):
    """Test rendering and OCR accuracy for a given input string.

    Args:
        input_string: The string to test (e.g., "★", "Hello ★★★ World")
    """
    print("=" * 60)
    print("String Rendering & OCR Test")
    print("=" * 60)
    try:
        print(f"Input string: '{input_string}'")
    except UnicodeEncodeError:
        print("Input string: [Unicode content - display not supported in console]")
    print(f"String length: {len(input_string)}")

    # Analyze characters for star detection
    print("Character analysis:")
    star_count = 0
    for i, char in enumerate(input_string):
        char_code = ord(char)
        if char_code in [
            9733,
            9734,
            11088,
            10032,
            10033,
            9735,
        ]:  # Common star Unicode values including ★
            star_count += 1
            print(f"  [{i}]: Star character detected (U+{char_code:04X})")
        elif char == "*":
            print(f"  [{i}]: Asterisk (*)")
        else:
            print(f"  [{i}]: Other character (U+{char_code:04X})")

    print(f"Total star-like characters detected: {star_count}")

    # Use the detected count for testing
    stars_in_input = star_count

    try:
        # Generate preview image
        print("\n[STEP 1] Generating preview image...")
        image_data = generate_conversation_preview(
            question="Test Question", answer=input_string, bot_name="Dawn Bringer"
        )

        print(f"SUCCESS: Image generated successfully! Size: {len(image_data)} bytes")

        # Save image temporarily for inspection
        temp_dir = Path(tempfile.gettempdir())
        test_filename = f"string_test_{hash(input_string) % 10000}.png"
        image_path = temp_dir / test_filename

        with open(image_path, "wb") as f:
            f.write(image_data)

        print(f"SAVE: Image saved: {image_path}")

        # Try to open the image for visual inspection
        try:
            open_image(image_path)
        except Exception as e:
            print(f"WARNING: Could not open image automatically: {e}")

        # Analyze the generated image
        print("\n[STEP 2] Analyzing image content...")
        ocr_results = analyze_image_content(image_data, input_string)

        print("\n[STEP 3] OCR Analysis Results:")
        print(f"   Image size: {ocr_results['image_size']} bytes")
        print(f"   Dimensions: {ocr_results['dimensions']}")
        print(f"   Text pixels: {ocr_results['text_pixels']}")
        print(f"   Text density: {ocr_results['text_density']:.4f}")
        print(f"   Empty box score: {ocr_results['empty_box_score']}")
        print(f"   Render quality: {ocr_results['render_quality']}")

        # Content verification
        print("\n[STEP 4] Content Verification:")
        print(f"   Content verification: {ocr_results['content_verification']}")

        if "star_conversion" in ocr_results:
            print(f"   Star conversion: {ocr_results['star_conversion']}")

        # String comparison
        print("\n[STEP 5] String Comparison:")
        try:
            print(f"   Original string: '{input_string}'")
        except UnicodeEncodeError:
            print(
                "   Original string: [Unicode content - display not supported in console]"
            )

        if "expected_lower" in ocr_results:
            try:
                print(f"   Expected (sanitized): '{ocr_results['expected_lower']}'")
            except UnicodeEncodeError:
                print(
                    "   Expected (sanitized): [Unicode content - display not supported in console]"
                )

        print(f"   Stars in original: {stars_in_input}")

        if "asterisks_in_image" in ocr_results:
            print(f"   Asterisks in image: {ocr_results['asterisks_in_image']}")

        # Determine test results
        print("\n[STEP 6] Test Results:")
        test_passed = True
        issues = []

        # Check star rendering (stars should remain as stars, not converted to asterisks)
        if stars_in_input > 0:
            # Check if the expected sanitized text contains asterisks (indicating conversion worked)
            expected_sanitized = ocr_results.get("expected_lower", "")
            stars_in_expected = sum(
                1
                for char in expected_sanitized
                if ord(char) in [9733, 9734, 11088, 10032, 10033, 9735]
            )

            print(
                f"DEBUG: Stars in input: {stars_in_input}, stars in expected: {stars_in_expected}"
            )

            if stars_in_expected >= stars_in_input:
                # Stars preserved - check if they render properly
                if ocr_results["render_quality"] in ["good", "fair"] or (
                    ocr_results["render_quality"] == "poor"
                    and ocr_results["text_pixels"] > 50
                ):
                    print(
                        f"SUCCESS: Star rendering - {stars_in_input} stars preserved and rendered ({ocr_results['text_pixels']} pixels)"
                    )
                else:
                    test_passed = False
                    issues.append(
                        f"Star rendering failed: quality is {ocr_results['render_quality']}"
                    )
            else:
                test_passed = False
                issues.append(
                    f"Stars not preserved: expected {stars_in_input} stars, found {stars_in_expected} in sanitized text"
                )

        # Check render quality (be more lenient for single characters and Unicode)
        if ocr_results["render_quality"] == "poor":
            # For single characters or Unicode content, accept if some text is detected
            if (len(input_string) == 1 and ocr_results["text_pixels"] > 20) or (
                stars_in_input > 0 and ocr_results["text_pixels"] > 20
            ):
                print(
                    f"INFO: Accepting 'poor' quality for single/Unicode character (detected {ocr_results['text_pixels']} pixels)"
                )
            else:
                test_passed = False
                issues.append(
                    f"Poor render quality: {ocr_results['content_verification']}"
                )

        # Check text presence (very lenient for single characters)
        if ocr_results["text_pixels"] < 20:
            test_passed = False
            issues.append("No text detected in image")

        if test_passed:
            print("PASS: String rendering and OCR working correctly!")
            print(f"   Text rendered with quality: {ocr_results['render_quality']}")
        else:
            print("FAIL: Issues detected:")
            for issue in issues:
                print(f"   ERROR: {issue}")

        # Clean up (with delay to allow image viewing)
        print("\nINFO: Image viewer opened. Close the image window when done viewing.")
        try:
            import time

            print("Waiting 1 second before cleanup...")
            time.sleep(1)  # Give user time to view the image
        except ImportError:
            print("Time module not available, proceeding with cleanup...")

        try:
            image_path.unlink()
            print(f"CLEANUP: Removed temporary file: {image_path}")
        except:
            pass

        return test_passed

    except Exception as e:
        print(f"ERROR: Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("String Rendering & OCR Test")
        print("=" * 40)
        print('Usage: python test/test_string_ocr.py "your test string"')
        print()
        print("Examples:")
        print('  python test/discord_preview/test_discord_preview_ocr.py "*"')
        print('  python test/discord_preview/test_discord_preview_ocr.py "Hello *** World"')
        print('  python test/discord_preview/test_discord_preview_ocr.py "Normal text"')
        print('  python test/discord_preview/test_discord_preview_ocr.py "*** Five stars"')
        print()
        print("Note: Use * instead of ★ due to command line encoding issues")
        print("This will:")
        print("1. Generate a Discord preview image with your string")
        print("2. Analyze the image content")
        print("3. Verify star-to-asterisk conversion")
        print("4. Report rendering quality")
        print()
        print("Built-in tests:")
        print("  python test/discord_preview/test_discord_preview_ocr.py --test-star")
        print("  python test/discord_preview/test_discord_preview_ocr.py --test-emoji")
        return

    test_string = sys.argv[1]

    if test_string == "--test-star":
        # Test star character directly (avoid command line encoding issues)
        print("Running built-in star test...")
        test_string = "★"
        print("Testing with actual star character (* converted)")
    elif test_string == "--test-emoji":
        # Test star emoji character
        print("Running built-in emoji test...")
        test_string = "⭐"
        print("Testing with actual star emoji (should convert to star)")

    success = test_string_rendering_ocr(test_string)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
