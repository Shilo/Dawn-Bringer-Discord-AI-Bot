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
    """Generates Discord preview images with conversation text."""

    # Discord embed image dimensions (1200x630 is optimal for Discord)
    WIDTH = 1200
    HEIGHT = 630

    # Colors (matching Discord's dark theme)
    BG_COLOR = (54, 57, 63)  # Discord dark background
    TEXT_COLOR = (255, 255, 255)  # White text
    ACCENT_COLOR = (88, 101, 242)  # Discord blue
    SECONDARY_COLOR = (185, 187, 190)  # Light gray

    # Typography
    TITLE_FONT_SIZE = 48
    BODY_FONT_SIZE = 32
    FOOTER_FONT_SIZE = 24

    # Spacing and margins
    MARGIN = 60
    TITLE_BOTTOM_MARGIN = 40
    LINE_SPACING = 8
    MAX_BODY_LINES = 6

    def __init__(self):
        """Initialize the image generator with fonts."""
        # Try to load fonts, fall back to default if not available
        try:
            # Try system fonts first
            self.title_font = ImageFont.truetype("arial.ttf", self.TITLE_FONT_SIZE)
            self.body_font = ImageFont.truetype("arial.ttf", self.BODY_FONT_SIZE)
            self.footer_font = ImageFont.truetype("arial.ttf", self.FOOTER_FONT_SIZE)
        except OSError:
            try:
                # Try alternative font names
                self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", self.TITLE_FONT_SIZE)
                self.body_font = ImageFont.truetype("DejaVuSans.ttf", self.BODY_FONT_SIZE)
                self.footer_font = ImageFont.truetype("DejaVuSans.ttf", self.FOOTER_FONT_SIZE)
            except OSError:
                # Fall back to default font
                self.title_font = ImageFont.load_default()
                self.body_font = ImageFont.load_default()
                self.footer_font = ImageFont.load_default()

                # Scale up default font sizes since they're small
                self.title_font = self._scale_font(self.title_font, 2.0)
                self.body_font = self._scale_font(self.body_font, 1.5)
                self.footer_font = self._scale_font(self.footer_font, 1.2)

    def _scale_font(self, font: ImageFont.FreeTypeFont, scale: float) -> ImageFont.FreeTypeFont:
        """Scale a font by creating a new one with scaled size (for default font fallback)."""
        # This is a workaround since we can't directly scale FreeTypeFont objects
        return font

    def sanitize_text(self, text: str) -> str:
        """Sanitize text for image rendering by removing markdown and normalizing whitespace.

        Args:
            text: Raw text that may contain markdown formatting

        Returns:
            Cleaned text suitable for image rendering
        """
        if not text:
            return ""

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

    def generate_preview_image(self, question: str, answer: str, bot_name: str = "Dawn Bringer") -> bytes:
        """Generate a Discord preview image with the conversation content.

        Args:
            question: The user's question
            answer: The AI's response
            bot_name: Name of the AI bot (default: "Dawn Bringer")

        Returns:
            PNG image data as bytes
        """
        # Create new image with Discord's preferred dimensions
        image = Image.new('RGB', (self.WIDTH, self.HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(image)

        # Sanitize and prepare text
        clean_question = self.sanitize_text(question)
        clean_answer = self.sanitize_text(answer)

        # Wrap question text (title)
        max_title_width = self.WIDTH - (self.MARGIN * 2)
        question_lines = self.wrap_text(clean_question, self.title_font, max_title_width)

        # Limit question to 2 lines maximum
        if len(question_lines) > 2:
            question_lines = question_lines[:2]
            if question_lines:
                question_lines[-1] = self._truncate_text_to_width(question_lines[-1], self.title_font, max_title_width)

        # Wrap answer text (body)
        max_body_width = self.WIDTH - (self.MARGIN * 2)
        answer_lines = self.wrap_text(clean_answer, self.body_font, max_body_width)

        # Limit answer to MAX_BODY_LINES
        if len(answer_lines) > self.MAX_BODY_LINES:
            answer_lines = answer_lines[:self.MAX_BODY_LINES]
            if answer_lines:
                answer_lines[-1] = self._truncate_text_to_width(answer_lines[-1], self.body_font, max_body_width)

        # Draw question (title) - white, bold, larger
        y_position = self.MARGIN
        for line in question_lines:
            draw.text((self.MARGIN, y_position), line, font=self.title_font, fill=self.TEXT_COLOR)
            bbox = self.title_font.getbbox(line)
            y_position += bbox[3] - bbox[1] + self.LINE_SPACING

        # Add some space after title
        y_position += self.TITLE_BOTTOM_MARGIN

        # Draw answer (body) - light gray, smaller
        for line in answer_lines:
            draw.text((self.MARGIN, y_position), line, font=self.body_font, fill=self.SECONDARY_COLOR)
            bbox = self.body_font.getbbox(line)
            y_position += bbox[3] - bbox[1] + self.LINE_SPACING

        # Draw footer with bot name and branding
        footer_text = f"Run! Goddess AI • {bot_name}"
        # Position footer at bottom right
        bbox = self.footer_font.getbbox(footer_text)
        footer_x = self.WIDTH - self.MARGIN - (bbox[2] - bbox[0])
        footer_y = self.HEIGHT - self.MARGIN - (bbox[3] - bbox[1])
        draw.text((footer_x, footer_y), footer_text, font=self.footer_font, fill=self.ACCENT_COLOR)

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
    """Generate a Discord preview image for a conversation.

    Args:
        question: The user's question
        answer: The AI's response
        bot_name: Name of the AI bot

    Returns:
        PNG image data as bytes
    """
    generator = get_preview_generator()
    return generator.generate_preview_image(question, answer, bot_name)