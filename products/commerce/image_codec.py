"""Safely decode merchant uploads and strip metadata before public delivery.

Only authenticated merchants can upload. Pillow fully decodes the image, applies
orientation, limits pixel work and produces a new JPEG. Untrusted original bytes,
EXIF and embedded profiles are never served back to storefront visitors.
"""
from __future__ import annotations

from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from storage import CommerceError

MAX_UPLOAD = 2_000_000
MAX_IMAGE = 500_000
MAX_PIXELS = 8_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
ACCEPTED = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def normalize_product_photo(raw: bytes, media_type: str) -> bytes:
    if media_type not in ACCEPTED:
        raise CommerceError("unsupported_image_type", 415)
    if not isinstance(raw,bytes) or not 1 <= len(raw) <= MAX_UPLOAD:
        raise CommerceError("image_size_invalid", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error",Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as uploaded:
                if uploaded.format != ACCEPTED[media_type]:
                    raise CommerceError("image_type_mismatch", 415)
                if (uploaded.width < 1 or uploaded.height < 1 or
                        uploaded.width * uploaded.height > MAX_PIXELS):
                    raise CommerceError("image_dimensions_invalid")
                uploaded.load()
                img = ImageOps.exif_transpose(uploaded)
                img.thumbnail((960,960),Image.Resampling.LANCZOS)
                if "A" in img.getbands():
                    background = Image.new("RGB",img.size,(255,255,255))
                    background.paste(img,mask=img.getchannel("A"))
                    img = background
                else:
                    img = img.convert("RGB")
                output=BytesIO()
                img.save(output,format="JPEG",quality=82,optimize=True)
                data=output.getvalue()
                if len(data)>MAX_IMAGE:
                    output=BytesIO()
                    img.save(output,format="JPEG",quality=65,optimize=True)
                    data=output.getvalue()
                if not 1<=len(data)<=MAX_IMAGE:
                    raise CommerceError("image_too_complex", 413)
                return data
    except CommerceError:
        raise
    except (OSError,ValueError,UnidentifiedImageError,Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise CommerceError("invalid_product_image") from exc
