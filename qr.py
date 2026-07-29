"""BUS XPERIENCE — QR code généré localement.

Aucun service externe: le SVG est calculé sur cette machine avec la
bibliothèque `qrcode` (pure Python, aucune image binaire, aucun réseau).
Interdiction absolue d'appeler une API de génération de QR code tierce, qui
recevrait l'URL et implicitement une trace du visiteur.
"""
from __future__ import annotations

import io

import qrcode
import qrcode.image.svg


def qr_svg(data: str, box_size: int = 8, border: int = 2) -> str:
    img = qrcode.make(
        data,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=box_size,
        border=border,
    )
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")
