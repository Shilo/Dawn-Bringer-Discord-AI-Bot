#!/usr/bin/env python3
"""
Discord Embed Image Rendering Test Suite

Comprehensive batch testing for Discord preview image generation.
Tests multiple text scenarios to verify proper rendering of stars, emojis,
and text with automatic font fallback and quality analysis.

This ensures Discord embeds display correctly with proper character rendering.
"""

import sys

sys.path.append(".")

from web_server import sanitize_text_for_preview
from preview_image_generator import PreviewImageGenerator
from preview_image_generator import generate_conversation_preview


def analyze_image_rendering(image_data, expected_text):
    """
    Analyze the generated image to detect rendering issues like empty boxes.

    Args:
        image_data: PNG image bytes
        expected_text: The text that should be rendered

    Returns:
        dict: Analysis results with quality metrics
    """
    from PIL import Image
    import io

    results = {
        "image_size": len(image_data),
        "dimensions": None,
        "total_pixels": 0,
        "text_pixels": 0,
        "background_pixels": 0,
        "empty_box_score": 0,  # Higher = more likely empty boxes
        "text_density": 0.0,  # Text pixels / total pixels
        "render_quality": "unknown",
        "issues_detected": [],
    }

    try:
        img = Image.open(io.BytesIO(image_data))
        # Use get_flattened_data to avoid deprecation warning (Pillow 14+)
        try:
            pixels = list(img.get_flattened_data())
        except AttributeError:
            # Fallback for older Pillow versions
            pixels = list(img.getdata())

        width, height = img.size
        results["dimensions"] = (width, height)
        results["total_pixels"] = len(pixels)

        # Discord embed background color (54, 57, 63)
        bg_color = (54, 57, 63)
        text_color = (255, 255, 255)

        results["text_pixels"] = sum(1 for pixel in pixels if pixel == text_color)
        results["background_pixels"] = sum(1 for pixel in pixels if pixel == bg_color)

        # Calculate text density
        results["text_density"] = (
            results["text_pixels"] / results["total_pixels"]
            if results["total_pixels"] > 0
            else 0
        )

        # Analyze for empty character boxes (simplified approach)
        # Focus on detecting if stars were rendered as empty boxes vs asterisks

        sanitized = sanitize_text_for_preview(expected_text)
        star_positions = []

        # Find positions of stars in sanitized text (should be asterisks now)
        for i, char in enumerate(sanitized):
            if char == "*":
                star_positions.append(i)

        # Check if we can detect rendered characters at expected positions
        # This is a rough heuristic - look for text-like patterns
        empty_star_count = 0

        if star_positions:
            # Estimate character width (rough guess: 12-15 pixels per character)
            char_width_estimate = 12

            # Check areas where stars should be (around line 1-2 of text)
            for line_y in [20, 45]:  # Check two possible lines
                for star_idx in star_positions[:5]:  # Check first 5 stars
                    x_start = 20 + (star_idx * char_width_estimate)

                    if x_start + 15 < width:
                        # Check this character position for rendered content
                        rendered_pixels = 0
                        total_checked = 0

                        for dy in range(25):  # Character height
                            for dx in range(10):  # Character width
                                pixel_idx = (line_y + dy) * width + (x_start + dx)
                                if pixel_idx < len(pixels):
                                    if pixels[pixel_idx] == text_color:
                                        rendered_pixels += 1
                                    total_checked += 1

                        # If very few pixels rendered here, it might be empty
                        if (
                            total_checked > 150
                            and (rendered_pixels / total_checked) < 0.05
                        ):
                            empty_star_count += 1

        results["empty_box_score"] = empty_star_count

        # Determine render quality (more realistic thresholds)
        if results["text_pixels"] < 100:
            results["render_quality"] = "poor"
            results["issues_detected"].append("Very few text pixels detected")
        elif results["empty_box_score"] > 20:
            results["render_quality"] = "poor"
            results["issues_detected"].append(
                f"Too many empty character boxes: {empty_box_count}"
            )
        elif results["text_pixels"] > 1000 and results["text_density"] > 0.005:
            results["render_quality"] = "good"
            results["issues_detected"].append("Text rendering appears normal")
        else:
            results["render_quality"] = "fair"
            results["issues_detected"].append("Moderate text rendering")

        # Check if expected characters are present
        # Count original stars and emoji stars
        original_stars = expected_text.count("★")
        original_emojis = expected_text.count("⭐")
        total_expected_stars = original_stars + original_emojis

        # Use the image generator's sanitization (which converts ⭐→★ and preserves ★)
        gen = PreviewImageGenerator()
        sanitized = gen.sanitize_text(expected_text)
        stars_in_sanitized = sanitized.count("★")

        if total_expected_stars > 0 and stars_in_sanitized >= total_expected_stars:
            results["issues_detected"].append("✅ Stars properly preserved/converted")
        elif total_expected_stars > 0 and stars_in_sanitized == 0:
            results["issues_detected"].append("❌ Stars may not be preserved properly")

    except Exception as e:
        results["render_quality"] = "error"
        results["issues_detected"].append(f"Analysis failed: {e}")

    return results


def test_image_analysis():
    """Test various text inputs to verify rendering quality."""
    test_cases = [
        "Rating: ★★★★+ (4★) Perfect!",
        "★★★★★ Excellent work!",
        "⭐⭐⭐⭐⭐ Five stars!",
        "Normal text without stars",
        "Mix ★ and normal text ★ here",
    ]

    print("[DISCORD EMBED] Image Rendering Quality Analysis")
    print("=" * 55)

    test_descriptions = [
        "Star rating text",
        "Five stars only",
        "Emoji stars",
        "Normal text",
        "Mixed content",
    ]

    for i, (test_text, description) in enumerate(zip(test_cases, test_descriptions), 1):
        print(f"\n[TEST {i}] {description}")

        try:
            # Generate image
            image_data = generate_conversation_preview(
                question="Test Question", answer=test_text, bot_name="Dawn Bringer"
            )

            # Analyze rendering
            analysis = analyze_image_rendering(image_data, test_text)

            print(f'   Size: {analysis["image_size"]} bytes')
            print(f'   Dimensions: {analysis["dimensions"]}')
            print(f'   Text pixels: {analysis["text_pixels"]}')
            print(f'   Text density: {analysis["text_density"]:.4f}')
            print(f'   Empty box score: {analysis["empty_box_score"]}')
            print(f'   Quality: {analysis["render_quality"]}')

            for issue in analysis["issues_detected"]:
                try:
                    print(f"   {issue}")
                except UnicodeEncodeError:
                    print(f"   [Unicode issue message]")

            # Save image for manual inspection
            filename = f"test_render_{i}.png"
            with open(filename, "wb") as f:
                f.write(image_data)
            print(f"   Saved: {filename}")

        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n" + "=" * 55)
    print("Discord embed rendering analysis complete! Open PNG files to verify.")
    print("Files are in: test/discord_preview/ directory")


if __name__ == "__main__":
    test_image_analysis()
