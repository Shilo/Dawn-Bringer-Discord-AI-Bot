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
        # Try to load system font, fall back to default if not available
        try:
            # Try system fonts first
            self.font = ImageFont.truetype("arial.ttf", self.FIXED_FONT_SIZE)
        except OSError:
            try:
                # Try alternative font names
                self.font = ImageFont.truetype("DejaVuSans.ttf", self.FIXED_FONT_SIZE)
            except OSError:
                # Fall back to default font
                self.font = ImageFont.load_default()
                # Scale up default font size
                self.font = self._scale_font(self.font, self.FIXED_FONT_SIZE / 12.0)

    def _scale_font(self, font: ImageFont.FreeTypeFont, scale: float) -> ImageFont.FreeTypeFont:
        """Scale a font by creating a new one with scaled size (for default font fallback)."""
        # This is a workaround since we can't directly scale FreeTypeFont objects
        return font

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

        # Ensure proper Unicode encoding/decoding to handle special characters
        try:
            # Try to encode and decode as UTF-8 to handle any encoding issues
            text = text.encode('utf-8').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            # If encoding fails, keep original text
            pass

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
            bbox = font.getbbox(truncated)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                best_fit = truncated
                low = mid + 1
            else:
                high = mid - 1

        return best_fit

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
        bbox = self.font.getbbox("Ag")  # Use 'Ag' to get typical line height
        line_height = bbox[3] - bbox[1] + self.LINE_SPACING
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

            # Draw the text
            draw.text((x_position, y_position), line, font=self.font, fill=self.TEXT_COLOR)

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