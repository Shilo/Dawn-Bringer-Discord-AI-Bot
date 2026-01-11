"""
Discord preview image generator for shared conversations.

This module generates preview images for Discord embeds, similar to ChatGPT's implementation.
Images are created dynamically based on the conversation content.
"""

import re
from io import BytesIO
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import textwrap


class PreviewImageGenerator:
    """Generates Discord preview images showing only answer text filling the entire canvas."""

    # Optimized image dimensions (1047x550 for better aspect ratio)
    WIDTH = 1047
    HEIGHT = 550

    # Colors (matching Discord's dark theme)
    BG_COLOR = (54, 57, 63)  # Discord dark background
    TEXT_COLOR = (255, 255, 255)  # White text (same as question color used to be)

    # Typography - fixed size for consistent layout
    FIXED_FONT_SIZE = 48

    # Spacing and margins - small margins for top-left alignment
    MARGIN = 20
    LINE_SPACING = 8

    def __init__(self):
        """Initialize the image generator with fonts."""
        # Try multiple fonts that support Unicode characters
        font_options = [
            ("arial.ttf", self.FIXED_FONT_SIZE),
            ("DejaVuSans.ttf", self.FIXED_FONT_SIZE),
            ("DejaVuSans-Bold.ttf", self.FIXED_FONT_SIZE),
            ("LiberationSans-Regular.ttf", self.FIXED_FONT_SIZE),
            ("FreeSans.ttf", self.FIXED_FONT_SIZE),
            ("tahoma.ttf", self.FIXED_FONT_SIZE),
            ("verdana.ttf", self.FIXED_FONT_SIZE),
            ("georgia.ttf", self.FIXED_FONT_SIZE),
            ("times.ttf", self.FIXED_FONT_SIZE),
            ("cour.ttf", self.FIXED_FONT_SIZE),
        ]

        self.font = None
        self.font_name = None

        for font_name, font_size in font_options:
            try:
                self.font = ImageFont.truetype(font_name, font_size)
                self.font_name = font_name

                # Test if the font can render our key characters
                test_img = Image.new('RGB', (100, 50), (255, 255, 255))
                test_draw = ImageDraw.Draw(test_img)

                # Test rendering star and dash characters
                test_text = '★‑ABC123'
                test_draw.text((10, 10), test_text, font=self.font, fill=(0, 0, 0))

                # Check if the star character actually rendered (not as empty square)
                pixels = list(test_img.getdata())
                # Look for non-white pixels in the area where star should be
                star_area_pixels = []
                for y in range(10, 25):  # Approximate star area
                    for x in range(10, 25):
                        if x < 100 and y < 50:  # Bounds check
                            star_area_pixels.append(pixels[y * 100 + x])

                # If we have some non-white pixels in star area, font likely supports it
                non_white_pixels = sum(1 for pixel in star_area_pixels if pixel != (255, 255, 255))
                if non_white_pixels > 5:  # Lower threshold for "rendered" character
                    break

            except (OSError, UnicodeEncodeError, IOError):
                continue

        # If no TrueType font worked, fall back to default
        if self.font is None or self.font_name is None:
            self.font = ImageFont.load_default()
            self.font_name = "default"
            # Scale up default font size
            self.font = self._scale_font(self.font, self.FIXED_FONT_SIZE / 12.0)

    def _scale_font(self, font: ImageFont.FreeTypeFont, scale: float) -> ImageFont.FreeTypeFont:
        """Scale a font by creating a new one with scaled size (for default font fallback)."""
        # This is a workaround since we can't directly scale FreeTypeFont objects
        return font

    def _can_render_star(self) -> bool:
        """Check if the current font can render the star character properly."""
        if not hasattr(self.font, 'getbbox'):
            return False

        try:
            # Create a small test image
            test_img = Image.new('RGB', (30, 20), (255, 255, 255))
            test_draw = ImageDraw.Draw(test_img)

            # Render the star character
            test_draw.text((5, 2), '★', font=self.font, fill=(0, 0, 0))

            # Check if any pixels changed (indicating the character was rendered)
            pixels = list(test_img.getdata())
            changed_pixels = sum(1 for pixel in pixels if pixel != (255, 255, 255))

            # If we have at least some changed pixels, the star likely rendered
            return changed_pixels > 5

        except Exception:
            return False

    def sanitize_text(self, text: str) -> str:
        """Sanitize text for image rendering by removing markdown and normalizing whitespace.

        Args:
            text: Raw text that may contain markdown formatting

        Returns:
            Cleaned text suitable for image rendering with proper Unicode handling
        """
        if not text:
            return ""

        # Handle as string to preserve Unicode
        text = str(text)

        # Remove markdown formatting (similar to web_server.py sanitize_text_for_preview)
        # Remove code blocks (```code```)
        text = re.sub(r'```[\s\S]*?```', '', text, flags=re.DOTALL)
        # Remove inline code (`code`)
        text = re.sub(r'`([^`\n]+)`', r'\1', text)
        # Remove bold/italic (**text**, *text*, ***text***, __text__, _text_)
        text = re.sub(r'\*\*\*([^*\n]+)\*\*\*', r'\1', text)  # ***bold italic***
        text = re.sub(r'\*\*([^*\n]+)\*\*', r'\1', text)      # **bold**
        text = re.sub(r'__([^_\n]+)__', r'\1', text)          # __bold__
        text = re.sub(r'\*([^*\n]+)\*', r'\1', text)          # *italic*
        text = re.sub(r'_([^_\n]+)_', r'\1', text)            # _italic_
        # Remove headers (# ## ### etc.)
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        # Remove links [text](url) but keep the text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove strikethrough (~~text~~)
        text = re.sub(r'~~([^~\n]+)~~', r'\1', text)
        # Remove spoilers ||text||
        text = re.sub(r'\|\|([^\|\n]+)\|\|', r'\1', text)
        # Remove list markers (-, *, +, numbers)
        text = re.sub(r'^[\s]*[-\*\+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)

        # Normalize whitespace
        # Replace newlines with spaces
        text = text.replace('\n', ' ').replace('\r', ' ')
        # Remove extra spaces and tabs
        text = re.sub(r'\s+', ' ', text)
        # Strip leading/trailing whitespace
        text = text.strip()

        # Replace problematic Unicode characters that don't render well
        # Replace star emojis with simple star symbols
        text = text.replace('⭐', '★')
        text = text.replace('⭐️', '★')

        # Always replace stars with asterisks for consistent rendering
        # Star characters can cause issues with font rendering even when fonts claim to support them
        text = text.replace('★', '*')

        return text


    def wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Wrap text to fit within a maximum width.

        Args:
            text: Text to wrap
            font: Font to use for measuring text
            max_width: Maximum width in pixels

        Returns:
            List of text lines that fit within max_width
        """
        if not text:
            return []

        # First, wrap text by words to handle long lines
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            # Check if adding this word would exceed the width
            test_line = current_line + " " + word if current_line else word
            try:
                bbox = font.getbbox(test_line)
                if bbox[2] - bbox[0] <= max_width:
                    current_line = test_line
                else:
                    # If current line is not empty, add it to lines
                    if current_line:
                        lines.append(current_line)
                    current_line = word

                    # Check if single word is too long
                    bbox = font.getbbox(current_line)
                    if bbox[2] - bbox[0] > max_width:
                        # Word is too long, truncate it
                        current_line = self._truncate_text_to_width(current_line, font, max_width)
            except (UnicodeEncodeError, UnicodeDecodeError, OSError) as e:
                # If we can't measure this line, it might be due to Unicode issues
                # Try to identify and fix the problematic characters
                if '★' in test_line:
                    # If the line contains stars, try a simpler measurement
                    try:
                        # Replace stars temporarily for measurement
                        measure_line = test_line.replace('★', '*')
                        bbox = font.getbbox(measure_line)
                        if bbox[2] - bbox[0] <= max_width:
                            current_line = test_line  # Keep original with stars
                        else:
                            if current_line:
                                lines.append(current_line)
                            current_line = word
                    except:
                        # If still failing, make it safe
                        safe_test_line = self._make_text_safe_for_font(test_line)
                        current_line = safe_test_line
                else:
                    # For other Unicode issues, make the text safe
                    safe_test_line = self._make_text_safe_for_font(test_line)
                    try:
                        bbox = font.getbbox(safe_test_line)
                        if bbox[2] - bbox[0] <= max_width:
                            current_line = safe_test_line
                        else:
                            if current_line:
                                lines.append(current_line)
                            current_line = self._make_text_safe_for_font(word)
                    except:
                        # If still failing, just use a safe version
                        if current_line:
                            lines.append(current_line)
                        current_line = "?"  # Safe fallback

        # Add the last line
        if current_line:
            lines.append(current_line)

        return lines

    def _truncate_text_to_width(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
        """Truncate text to fit within max_width by removing characters from the end.

        Args:
            text: Text to truncate
            font: Font to use for measuring
            max_width: Maximum width in pixels

        Returns:
            Truncated text that fits within max_width
        """
        if not text:
            return ""

        # Binary search to find the maximum length that fits
        low, high = 0, len(text)
        best_fit = ""

        while low <= high:
            mid = (low + high) // 2
            truncated = text[:mid] + "..." if mid < len(text) else text
            try:
                bbox = font.getbbox(truncated)
                width = bbox[2] - bbox[0]

                if width <= max_width:
                    best_fit = truncated
                    low = mid + 1
                else:
                    high = mid - 1
            except (UnicodeEncodeError, UnicodeDecodeError, OSError):
                # If measurement fails due to Unicode issues, try with safe text
                safe_truncated = self._make_text_safe_for_font(truncated)
                try:
                    bbox = font.getbbox(safe_truncated)
                    width = bbox[2] - bbox[0]

                    if width <= max_width:
                        best_fit = truncated  # Keep original, not safe version
                        low = mid + 1
                    else:
                        high = mid - 1
                except:
                    # If still failing, reduce length
                    high = mid - 1

        return best_fit

    def _make_text_safe_for_font(self, text: str) -> str:
        """Replace Unicode characters that don't render well with safe alternatives.

        Args:
            text: Text that may contain problematic Unicode characters

        Returns:
            Text with problematic characters replaced
        """
        # Replace various emoji characters with simple alternatives
        replacements = {
            '⭐': '★',
            '⭐️': '★',
            '✨': '*',
            '🌟': '★',
            '🔥': '!',
            '💫': '*',
            '🎉': '!',
            '🎊': '!',
            '💥': '!',
            '⚡': '!',
            '❤️': '<3',
            '💔': '</3',
            '👍': '+',
            '👎': '-',
            '👌': 'OK',
            '🤔': '?',
            '😊': ':)',
            '😢': ':(',
            '😮': ':O',
            '😀': ':D',
            '😎': 'B)',
            '🤡': ':C',
            '💯': '100',
            '🔒': '[LOCK]',
            '🔓': '[UNLOCK]',
            '📌': '[PIN]',
            '⚠️': '!',
            '❌': 'X',
            '✅': '✓',
            '➡️': '->',
            '⬅️': '<-',
            '⬆️': '^',
            '⬇️': 'v',
        }

        safe_text = text
        for original, replacement in replacements.items():
            safe_text = safe_text.replace(original, replacement)

        # Allow common Unicode symbols that should work with standard fonts
        # Only replace truly problematic characters
        allowed_chars = set('★‑—–…′″‴‵‶‷‸‹›※‼‽‾⁋⁌⁍⁎⁏⁐⁑⁒⁓⁔⁕⁖⁗⁘⁙⁚⁛⁜⁝⁞')
        allowed_chars.update('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')
        allowed_chars.update(' !@#$%^&*()_+-=[]{}|;:,.<>?/~`"\\\'')
        allowed_chars.update('áéíóúàèìòùâêîôûäëïöüÿçñÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÄËÏÖÜŸÇÑ')
        allowed_chars.update('¡¿€£¥¢©®™°§¶†‡•·‚„"''""''""')

        # Special handling - ensure star character is always allowed
        allowed_chars.add('★')

        # Handle Unicode issues by working with the string as-is
        # If the text contains stars, make sure they stay as stars
        if '★' in safe_text:
            # If stars are present and valid, return as-is
            return safe_text

        # For other cases, do minimal filtering
        import unicodedata
        safe_chars = []
        try:
            # Try to process each character individually
            for char in safe_text:
                try:
                    # Check if character is valid Unicode
                    ord(char)  # This will fail for invalid sequences

                    # Allow ASCII and common Unicode characters
                    if ord(char) < 128 or char in allowed_chars:
                        safe_chars.append(char)
                    else:
                        # Check if it's a known problematic character
                        name = unicodedata.name(char, None)
                        if name and ('EMOJI' in name.upper() or ord(char) > 0xFFFF):
                            # Replace emoji/unicode symbols outside BMP with safe alternatives
                            if 'STAR' in name.upper():
                                safe_chars.append('★')
                            elif 'HEART' in name.upper():
                                safe_chars.append('<3')
                            elif 'THUMBS' in name.upper() and 'UP' in name.upper():
                                safe_chars.append('+')
                            elif 'THUMBS' in name.upper() and 'DOWN' in name.upper():
                                safe_chars.append('-')
                            else:
                                safe_chars.append('?')  # Generic replacement for truly problematic chars
                        else:
                            # Allow other Unicode characters
                            safe_chars.append(char)
                except (ValueError, TypeError, UnicodeDecodeError):
                    # Skip invalid characters
                    continue
        except Exception:
            # If anything goes wrong with Unicode processing, return safe text
            return safe_text.replace('⭐', '★').replace('⭐️', '★')

        return ''.join(safe_chars)

    def truncate_text_to_fit(self, text: str) -> str:
        """Truncate text to fit within the image bounds using fixed font size.

        Args:
            text: Text to truncate

        Returns:
            Truncated text that fits within image bounds
        """
        if not text:
            return ""

        available_width = self.WIDTH - (self.MARGIN * 2)
        available_height = self.HEIGHT - (self.MARGIN * 2)

        # Get line height for the fixed font
        try:
            bbox = self.font.getbbox("Ag")  # Use 'Ag' to get typical line height
            line_height = bbox[3] - bbox[1] + self.LINE_SPACING
        except (UnicodeEncodeError, UnicodeDecodeError, OSError):
            # If measurement fails, try with simple ASCII
            try:
                bbox = self.font.getbbox("Ag")
                line_height = bbox[3] - bbox[1] + self.LINE_SPACING
            except:
                # Fallback line height if measurement fails
                line_height = self.FIXED_FONT_SIZE + self.LINE_SPACING

        max_lines = int(available_height // line_height)

        if max_lines <= 0:
            return ""

        # First, wrap text normally
        lines = self.wrap_text(text, self.font, available_width)

        # If we have too many lines, truncate the text and try again
        while len(lines) > max_lines and len(text) > 10:
            # Remove some characters and try again
            text = text[:-10] + "..."
            lines = self.wrap_text(text, self.font, available_width)

        # Return the truncated text
        return text

    def generate_preview_image(self, question: str, answer: str, bot_name: str = "Dawn Bringer") -> bytes:
        """Generate a Discord preview image with left-aligned text starting from top-left corner.

        Args:
            question: The user's question (ignored in output)
            answer: The AI's response (displayed with fixed font size)
            bot_name: Name of the AI bot (ignored in output)

        Returns:
            PNG image data as bytes
        """
        # Create new image with optimized dimensions
        image = Image.new('RGB', (self.WIDTH, self.HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Sanitize the answer text
        clean_answer = self.sanitize_text(answer)

        # Truncate text to fit within image bounds
        truncated_text = self.truncate_text_to_fit(clean_answer)

        # Wrap text with fixed font
        available_width = self.WIDTH - (self.MARGIN * 2)
        lines = self.wrap_text(truncated_text, self.font, available_width)

        # Draw all lines from top-left corner
        y_position = self.MARGIN
        for line in lines:
            # Left align each line (start from left margin)
            x_position = self.MARGIN

            # Try to draw the text, replace problematic characters if needed
            try:
                draw.text((x_position, y_position), line, font=self.font, fill=self.TEXT_COLOR)
            except (UnicodeEncodeError, UnicodeDecodeError, OSError):
                # If drawing fails, try to replace problematic characters
                safe_line = self._make_text_safe_for_font(line)
                draw.text((x_position, y_position), safe_line, font=self.font, fill=self.TEXT_COLOR)

            # Move to next line
            bbox = self.font.getbbox(line)
            line_height = bbox[3] - bbox[1]
            y_position += line_height + self.LINE_SPACING

        # Save to BytesIO and return bytes
        output = BytesIO()
        image.save(output, format='PNG')
        output.seek(0)
        return output.getvalue()


# Global instance for reuse
_generator_instance: Optional[PreviewImageGenerator] = None


def get_preview_generator() -> PreviewImageGenerator:
    """Get the global preview image generator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = PreviewImageGenerator()
    return _generator_instance


def generate_conversation_preview(question: str, answer: str, bot_name: str = "Dawn Bringer") -> bytes:
    """Generate a Discord preview image with left-aligned text starting from top-left corner.

    Args:
        question: The user's question (ignored in output)
        answer: The AI's response (displayed with fixed font size, truncated to fit)
        bot_name: Name of the AI bot (ignored in output)

    Returns:
        PNG image data as bytes with optimized dimensions (1047x550)
    """
    generator = get_preview_generator()
    return generator.generate_preview_image(question, answer, bot_name)