"""
Discord preview image generator for shared conversations.

This version implements true font fallback for Pillow:
- Pillow does NOT do per-character font fallback.
- We load 3 fonts:
  - text font (Arial / DejaVu / etc.)
  - symbol font (Segoe UI Symbol / fallback) for ★
  - emoji font (Segoe UI Emoji / Noto Color Emoji / fallback) for ⭐
- We then draw text as "runs" so each glyph uses a font that supports it.

Cross-platform: Windows (Segoe fonts), Linux (DejaVu/Noto), macOS (system fonts).
"""

import os
import re
from io import BytesIO
from typing import Optional, List, Tuple, Dict
from PIL import Image, ImageDraw, ImageFont


class PreviewImageGenerator:
    # Image dimensions
    WIDTH = 1047
    HEIGHT = 550

    # Colors
    BG_COLOR = (54, 57, 63)
    TEXT_COLOR = (255, 255, 255)

    # Typography
    FIXED_FONT_SIZE = 48

    # Layout
    MARGIN = 20
    LINE_SPACING = 8

    def __init__(self):
        # Load fonts (best-effort)
        self.font_text = self._load_first_font(
            [
                "arial.ttf",
                "tahoma.ttf",
                "verdana.ttf",
                "DejaVuSans.ttf",
                "LiberationSans-Regular.ttf",
                "FreeSans.ttf",
            ],
            self.FIXED_FONT_SIZE,
            fallback_to_default=True,
        )

        # Symbol font (for ★ and other symbols) - prioritize Linux for Railway
        self.font_symbol = self._load_first_font(
            [
                # Linux first (Railway uses Linux containers)
                "DejaVuSans.ttf",  # Contains ★ on most Linux systems
                "DejaVuSerif.ttf",
                "LiberationSans-Regular.ttf",
                "FreeSans.ttf",
                # Windows
                "seguisym.ttf",
                "Segoe UI Symbol",
                # macOS
                "Apple Symbols",
                "Symbol",
            ],
            self.FIXED_FONT_SIZE,
            fallback_to_default=False,
        )

        # Emoji font (for ⭐ and other emoji) - prioritize Linux for Railway
        self.font_emoji = self._load_first_font(
            [
                # Linux (Railway)
                "NotoColorEmoji.ttf",
                "NotoEmoji-Regular.ttf",
                # Windows
                "seguiemj.ttf",
                "Segoe UI Emoji",
                # macOS
                "Apple Color Emoji",
            ],
            self.FIXED_FONT_SIZE,
            fallback_to_default=False,
        )

        # For any char not explicitly routed, we'll use this as default
        self.font = self.font_text
        self.font_name = self._font_debug_name(self.font_text)

        # Debug prints (optional)
        print(f"Text font:   {self._font_debug_name(self.font_text)}")
        print(
            f"Symbol font: {self._font_debug_name(self.font_symbol) if self.font_symbol else 'None'}"
        )
        print(
            f"Emoji font:  {self._font_debug_name(self.font_emoji) if self.font_emoji else 'None'}"
        )

        # Use fixed line height so emoji font doesn't clip or shift lines
        self._line_height_px = self.FIXED_FONT_SIZE

    # -------------------------
    # Public API
    # -------------------------
    def generate_preview_image(
        self, question: str, answer: str, bot_name: str = "Dawn Bringer"
    ) -> bytes:
        image = Image.new("RGB", (self.WIDTH, self.HEIGHT), self.BG_COLOR)
        draw = ImageDraw.Draw(image)

        clean_answer = self.sanitize_text(answer)
        truncated = self.truncate_text_to_fit(clean_answer, draw)

        available_width = self.WIDTH - (self.MARGIN * 2)
        lines = self.wrap_text(truncated, draw, available_width)

        y = self.MARGIN
        for line in lines:
            if y > self.HEIGHT - self.MARGIN - self._line_height_px:
                break
            self.draw_text_with_fallback(draw, (self.MARGIN, y), line, self.TEXT_COLOR)
            y += self._line_height_px + self.LINE_SPACING

        out = BytesIO()
        image.save(out, format="PNG")
        out.seek(0)
        return out.getvalue()

    # -------------------------
    # Sanitization
    # -------------------------
    def sanitize_text(self, text: str) -> str:
        """
        Keep this lightweight. Convert ⭐ to ★ for consistent rendering.
        """
        if not text:
            return ""

        text = str(text)

        # Remove markdown-ish blocks (optional; keep your original logic if you want)
        text = re.sub(r"```[\s\S]*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`\n]+)`", r"\1", text)

        # Convert star emoji to star symbol for consistent rendering
        text = text.replace("⭐", "★")

        # Remove emoji variation selectors (⭐️ => ⭐, but we already converted above)
        text = re.sub(r"[\uFE00-\uFE0F]", "", text)

        # Normalize whitespace
        text = text.replace("\n", " ").replace("\r", " ")
        text = re.sub(r"\s+", " ", text).strip()

        return text

    # -------------------------
    # Wrapping / truncation
    # -------------------------
    def wrap_text(
        self, text: str, draw: ImageDraw.ImageDraw, max_width: int
    ) -> List[str]:
        if not text:
            return []

        words = text.split()
        lines: List[str] = []
        current = ""

        for w in words:
            test = (current + " " + w) if current else w
            if self._measure_with_fallback(draw, test) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w

                # Single word too long: truncate
                if self._measure_with_fallback(draw, current) > max_width:
                    current = self._truncate_text_to_width(draw, current, max_width)

        if current:
            lines.append(current)

        return lines

    def truncate_text_to_fit(self, text: str, draw: ImageDraw.ImageDraw) -> str:
        if not text:
            return ""

        available_width = self.WIDTH - (self.MARGIN * 2)
        available_height = self.HEIGHT - (self.MARGIN * 2)
        max_lines = max(
            1, int(available_height // (self._line_height_px + self.LINE_SPACING))
        )

        lines = self.wrap_text(text, draw, available_width)
        while len(lines) > max_lines and len(text) > 10:
            text = text[:-10] + "..."
            lines = self.wrap_text(text, draw, available_width)

        return text

    def _truncate_text_to_width(
        self, draw: ImageDraw.ImageDraw, text: str, max_width: int
    ) -> str:
        low, high = 0, len(text)
        best = ""

        while low <= high:
            mid = (low + high) // 2
            candidate = text[:mid] + ("..." if mid < len(text) else "")
            if self._measure_with_fallback(draw, candidate) <= max_width:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1

        return best or "..."

    # -------------------------
    # Fallback drawing (key feature)
    # -------------------------
    def draw_text_with_fallback(
        self, draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, fill
    ):
        """
        Draw text using font runs with proper baseline alignment:
        - Default: text font
        - ★ uses symbol font (if loaded) - handles both ★ and converted ⭐
        - Fonts are baseline-aligned for consistent positioning
        """
        x, y = xy
        if not text:
            return

        font_text = self.font_text
        font_sym = self.font_symbol or font_text

        def pick_font(ch: str) -> ImageFont.FreeTypeFont:
            if ch == "★":
                return font_sym
            return font_text

        # Calculate baseline alignment offsets
        baseline_offsets = self._calculate_baseline_offsets()

        run_chars: List[str] = []
        run_font: Optional[ImageFont.FreeTypeFont] = None

        def flush():
            nonlocal x, run_chars, run_font
            if not run_chars or run_font is None:
                return
            s = "".join(run_chars)
            # Apply baseline offset for this font
            font_y = y + baseline_offsets.get(run_font, 0)
            draw.text((x, font_y), s, font=run_font, fill=fill)
            x += self._text_width(draw, s, run_font)
            run_chars = []

        for ch in text:
            f = pick_font(ch)
            if run_font is None:
                run_font = f
                run_chars.append(ch)
            elif f == run_font:
                run_chars.append(ch)
            else:
                flush()
                run_font = f
                run_chars.append(ch)

        flush()

    def _calculate_baseline_offsets(self) -> Dict[ImageFont.FreeTypeFont, int]:
        """
        Calculate baseline alignment offsets for different fonts.
        Returns a dict mapping font -> y-offset to align baselines.
        """
        offsets = {}

        # Use text font as reference (baseline = 0)
        font_text = self.font_text
        font_sym = self.font_symbol

        if font_sym and font_sym != font_text:
            # Calculate offset to align baselines
            # This is a heuristic based on typical font metrics
            try:
                # Get bounding boxes for a reference character
                ref_char = "A"

                # Text font baseline reference
                text_bbox = font_text.getbbox(ref_char)
                if text_bbox:
                    text_baseline = text_bbox[3]  # Bottom of bounding box

                    # Symbol font offset
                    sym_bbox = font_sym.getbbox(ref_char)
                    if sym_bbox:
                        sym_baseline = sym_bbox[3]
                        # Calculate offset to align baselines
                        offset = text_baseline - sym_baseline
                        offsets[font_sym] = offset
            except Exception:
                # If calculation fails, use a small default offset
                offsets[font_sym] = -2  # Slight upward adjustment for symbol fonts

        return offsets

    # -------------------------
    # Measurement using the same fallback routing
    # -------------------------
    def _measure_with_fallback(self, draw: ImageDraw.ImageDraw, text: str) -> float:
        """
        Measure by summing widths using the same routing rules as draw_text_with_fallback.
        This makes wrapping consistent with what you actually draw.
        """
        if not text:
            return 0.0

        font_text = self.font_text
        font_sym = self.font_symbol or font_text

        total = 0.0
        for ch in text:
            if ch == "★":
                total += self._text_width(draw, ch, font_sym)
            else:
                total += self._text_width(draw, ch, font_text)
        return total

    def _text_width(
        self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont
    ) -> float:
        try:
            return float(draw.textlength(text, font=font))
        except Exception:
            try:
                bbox = font.getbbox(text)
                return float((bbox[2] - bbox[0]) if bbox else 0.0)
            except Exception:
                # rough fallback
                return float(len(text) * (self.FIXED_FONT_SIZE * 0.6))

    # -------------------------
    # Font loading helpers
    # -------------------------
    def _load_first_font(
        self, candidates: List[str], size: int, fallback_to_default: bool
    ) -> Optional[ImageFont.FreeTypeFont]:
        for name in candidates:
            f = self._try_load_font(name, size)
            if f is not None:
                return f
        return ImageFont.load_default() if fallback_to_default else None

    def _try_load_font(self, name: str, size: int) -> Optional[ImageFont.FreeTypeFont]:
        # Try direct name (works on most systems)
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass

        # Windows font directory
        if os.name == "nt" and name.lower().endswith(".ttf"):
            p = os.path.join(r"C:\Windows\Fonts", name)
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass

        # Linux font directories (Railway uses Linux containers)
        if os.name == "posix":  # Linux/macOS
            linux_font_dirs = [
                "/usr/share/fonts/truetype",  # Debian/Ubuntu
                "/usr/share/fonts",  # Generic Linux
                "/usr/local/share/fonts",  # Some systems
            ]
            for font_dir in linux_font_dirs:
                if os.path.exists(font_dir):
                    # Try common subdirectories
                    for subdir in ["", "dejavu", "liberation", "freefont"]:
                        font_path = os.path.join(font_dir, subdir, name)
                        if os.path.exists(font_path):
                            try:
                                return ImageFont.truetype(font_path, size)
                            except Exception:
                                pass

        return None

    def _font_debug_name(self, font: Optional[ImageFont.FreeTypeFont]) -> str:
        if font is None:
            return "None"
        return getattr(font, "path", "loaded")


# Global instance
_generator_instance: Optional[PreviewImageGenerator] = None


def get_preview_generator() -> PreviewImageGenerator:
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = PreviewImageGenerator()
    return _generator_instance


def generate_conversation_preview(
    question: str, answer: str, bot_name: str = "Dawn Bringer"
) -> bytes:
    generator = get_preview_generator()
    return generator.generate_preview_image(question, answer, bot_name)
