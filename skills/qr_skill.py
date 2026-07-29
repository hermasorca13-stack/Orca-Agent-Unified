# skills/qr_skill.py — QR Code Skill (qrcode[pil]-backed)
"""
Full QR code generation using qrcode[pil] (Project Nayuki algorithm, 4.7k+ stars).
Supports PNG, SVG, ASCII, with full styling control.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
import io
import base64
import qrcode
from qrcode.image.pil import PilImage
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer, GappedSquareModuleDrawer, CircleModuleDrawer,
    RoundedModuleDrawer, VerticalBarsDrawer, HorizontalBarsDrawer
)
from qrcode.image.styles.colormasks import SolidFillColorMask, ImageColorMask
from PIL import Image

_NAME = "qr"
_DESCRIPTION = "Generate QR codes: PNG, SVG, ASCII, with styles (square/circle/rounded/bars), colors, and embedded logo."
_VERSION = "2.0.0"


def _module_drawer(style: str):
    s = (style or "square").lower()
    return {
        "square": SquareModuleDrawer(),
        "gapped": GappedSquareModuleDrawer(),
        "circle": CircleModuleDrawer(),
        "rounded": RoundedModuleDrawer(),
        "vertical_bars": VerticalBarsDrawer(),
        "horizontal_bars": HorizontalBarsDrawer(),
    }.get(s, SquareModuleDrawer())


# ---------- core builders ----------
def _build_qr(data: str, error_correction: str = "M", box_size: int = 10,
              border: int = 4, style: str = "square",
              fill_color: str = "black", back_color: str = "white",
              logo_path: Optional[str] = None):
    ec_map = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }
    qr = qrcode.QRCode(
        version=None,
        error_correction=ec_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M),
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    if logo_path:
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=_module_drawer(style),
            color_mask=ImageColorMask(color_mask_image=Image.open(logo_path).convert("RGBA")),
        )
    else:
        # SolidFillColorMask expects (back, front) — both must be int/tuple
        back = _parse_color(back_color)
        front = _parse_color(fill_color)
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=_module_drawer(style),
            color_mask=SolidFillColorMask(back_color=back, front_color=front),
        )
    return img


def _parse_color(c):
    """Accept hex string, named color, int, or tuple — return PIL-compatible RGB(A) tuple."""
    if isinstance(c, (tuple, list)):
        if len(c) == 4:
            return tuple(int(v) for v in c)
        return tuple(int(v) for v in c) + (255,)
    if isinstance(c, int):
        r = (c >> 16) & 0xFF
        g = (c >> 8) & 0xFF
        b = c & 0xFF
        return (r, g, b, 255)
    if isinstance(c, str):
        if c.startswith("#"):
            h = c.lstrip("#")
            if len(h) == 6:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
            if len(h) == 8:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
        try:
            from PIL import ImageColor
            return ImageColor.getcolor(c, "RGBA")
        except Exception:
            return (0, 0, 0, 255)
    return (0, 0, 0, 255)


# ---------- public ----------
def generate_png(data: str, error_correction: str = "M", box_size: int = 10,
                 border: int = 4, style: str = "square",
                 fill_color: str = "black", back_color: str = "white",
                 logo_path: Optional[str] = None) -> bytes:
    img = _build_qr(data, error_correction, box_size, border, style,
                    fill_color, back_color, logo_path)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_png_b64(data: str, **kwargs) -> str:
    return base64.b64encode(generate_png(data, **kwargs)).decode("ascii")


def generate_svg(data: str, error_correction: str = "M", box_size: int = 10,
                 border: int = 4, fill_color: str = "black", back_color: str = "white") -> str:
    """Generate an SVG QR code (via qrcode.image.svg.SvgImage)."""
    from qrcode.image.svg import SvgImage
    ec_map = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }
    qr = qrcode.QRCode(
        version=None,
        error_correction=ec_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M),
        box_size=box_size,
        border=border,
        image_factory=SvgImage,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image()
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


def generate_ascii(data: str, error_correction: str = "M", border: int = 2) -> str:
    """Generate a Unicode-block ASCII representation."""
    qr = qrcode.QRCode(
        version=None,
        error_correction={
            "L": qrcode.constants.ERROR_CORRECT_L,
            "M": qrcode.constants.ERROR_CORRECT_M,
            "Q": qrcode.constants.ERROR_CORRECT_Q,
            "H": qrcode.constants.ERROR_CORRECT_H,
        }.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M),
        box_size=1,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    lines = []
    for row in matrix:
        lines.append("".join("██" if cell else "  " for cell in row))
    return "\n".join(lines)


def save_png(data: str, output_path: str, **kwargs) -> Dict[str, Any]:
    png = generate_png(data, **kwargs)
    with open(output_path, "wb") as f:
        f.write(png)
    return {"path": output_path, "size_bytes": len(png), "format": "PNG"}


# ---------- meta ----------
def meta() -> Dict[str, Any]:
    return {
        "name": _NAME,
        "description": _DESCRIPTION,
        "version": _VERSION,
        "library": "qrcode[pil] (Project Nayuki algorithm)",
        "styles": ["square", "gapped", "circle", "rounded", "vertical_bars", "horizontal_bars"],
        "outputs": ["PNG", "SVG", "ASCII"],
        "error_correction_levels": ["L (~7%)", "M (~15%)", "Q (~25%)", "H (~30%)"],
    }
