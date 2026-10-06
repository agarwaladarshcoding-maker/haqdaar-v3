"""M4: what is done to a photo that came by SMS before the model reads it. Plain words."""
import io

from PIL import Image, ImageFilter

# One line added to the reader's instructions for these photos.
READ_NOTE = ("These pictures are tiny and blocky: a keypad phone sent them by SMS. Say only what you can really "
             "see. If you cannot tell, say so and give a low sure.")

LONG_SIDE = 512   # dots


def enlarge(jpeg: bytes, long_side: int = LONG_SIDE) -> bytes:
    """Make the small picture bigger (bicubic) and smooth the blocks a little. It adds no detail."""
    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    w, h = im.size
    if max(w, h) >= long_side:
        return jpeg
    k = long_side / max(w, h)
    im = im.resize((round(w * k), round(h * k)), Image.BICUBIC).filter(ImageFilter.SMOOTH)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue()
