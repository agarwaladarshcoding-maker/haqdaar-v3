"""M1: cut a photo into P: packets for sending by SMS. Plain words.

A packet looks like:
  P:<case>:<sent>:<place>:<stamp>:<k>/<n>:<step>:<len>:<hdr>:<dev>:<payload>
and the last packet of a photo ends with :<check>.
"""

import base64
import hashlib
import io
import zlib

from PIL import Image

from haqdaar.contracts import tunables

from .share import max_photos, share_parts

# Letters we may use in a packet: plain GSM letters only.
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
PART_LEN = 153  # letters in one SMS part

# Size ladder, biggest first. step = the index in this list. All cut at one quality.
SIZE_LADDER = (
    (192, 144),
    (176, 132),
    (160, 120),
    (144, 108),
    (128, 96),
    (112, 84),
    (96, 72),
    (80, 60),
    (64, 48),
)


def _open(image):
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, bytes):
        return Image.open(io.BytesIO(image)).convert("RGB")
    with open(image, "rb") as f:
        return Image.open(io.BytesIO(f.read())).convert("RGB")


def detail_window(img):
    """Most detailed half-frame window. 3x3 grid test of detail; middle on a tie."""
    w, h = img.size
    gray = img.convert("L")
    gray.thumbnail((96, 96))        # the test is on a small copy: a 12 MP photo is not walked pixel by pixel
    sw, sh = gray.size
    px = list(gray.tobytes())
    scores = []
    for cy in range(3):
        for cx in range(3):
            xs = range(cx * sw // 3, max(cx * sw // 3 + 1, (cx + 1) * sw // 3))
            ys = range(cy * sh // 3, max(cy * sh // 3 + 1, (cy + 1) * sh // 3))
            cell = [px[y * sw + x] for y in ys for x in xs]
            mean = sum(cell) / len(cell)
            var = sum((v - mean) ** 2 for v in cell) / len(cell)
            scores.append(var)
    if max(scores) - min(scores) < 1e-9:
        cx, cy = 1, 1  # flat picture: the middle is the fallback
    else:
        i = scores.index(max(scores))
        cx, cy = i % 3, i // 3
    ww, hh = w // 2, h // 2
    left = cx * w // 3 + w // 6 - ww // 2
    top = cy * h // 3 + h // 6 - hh // 2
    left = max(0, min(w - ww, left))
    top = max(0, min(h - hh, top))
    return (left, top, left + ww, top + hh)


def encode_jpeg(img, w, h, q):
    small = img.resize((w, h), Image.BICUBIC)
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=int(q))
    return buf.getvalue()


def split_header(data):
    """Cut a JPEG into (header, rest) at the end of the picture-start block."""
    i = data.find(b"\xff\xda")
    if i < 0:
        raise ValueError("no picture data in jpeg")
    end = i + 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return data[:end], data[end:]


def make_header(w, h, q):
    """The server's copy of the header: encode a small test picture, keep the head."""
    test = Image.new("RGB", (w, h), (128, 128, 128))
    return split_header(encode_jpeg(test, w, h, q))[0]


def stamp_of(data):
    """3 letters from a hash of the photo bytes. A re-sent photo gets a new one."""
    digest = hashlib.sha256(bytes(data)).digest()
    return "".join(B64[b & 0x3F] for b in digest[:3])


def check_of(data):
    """6 letters: CRC-32 of the whole picture bytes as sent. Only in the last packet."""
    crc = zlib.crc32(bytes(data)) & 0xFFFFFFFF
    out = []
    for shift in (30, 24, 18, 12, 6, 0):
        out.append(B64[(crc >> shift) & 0x3F])
    return "".join(out)


def _tag(k, n, case, sent, place, stamp, step, size, hdr, dev, last):
    head = "P:%s:%s:%s:%s:%d/%d:%d:%d:%d:%s:" % (
        case, sent, place, stamp, k, n, step, size, hdr, dev)
    return head, len(head) + (7 if last else 0)


def _plan(n_chars, case, sent, place, stamp, step, size, hdr, dev, packet_parts):
    """Fewest packets that hold n_chars of payload. Each packet is one long SMS."""
    per = packet_parts * PART_LEN
    n = 1
    while True:
        caps = [per - _tag(k, n, case, sent, place, stamp, step, size,
                           hdr, dev, k == n)[1] for k in range(1, n + 1)]
        if all(c > 0 for c in caps) and sum(caps) >= n_chars:
            return n, caps
        n += 1


def cut_photo(image, case, sent, place, dev="--", hdr=0, packet_parts=None,
              quality=None):
    """Cut one photo into P: packets. Biggest ladder step that fits the share wins."""
    for name, val in (("case", case), ("dev", dev)):
        val = str(val)
        if not val or ":" in val or "/" in val:
            raise ValueError("bad %s" % name)
    sent, place, hdr = int(sent), int(place), int(hdr)
    if sent < 1 or place < 1 or hdr not in (0, 1):
        raise ValueError("bad sent/place/hdr")
    if packet_parts is None:
        packet_parts = tunables.SMS_PACKET_PARTS
    if quality is None:
        quality = tunables.SMS_JPEG_Q
    packet_parts, quality = int(packet_parts), int(quality)

    img = _open(image)
    win = img.crop(detail_window(img))
    budget = share_parts(sent) * PART_LEN

    pick = None
    for step, (w, h) in enumerate(SIZE_LADDER):
        full = encode_jpeg(win, w, h, quality)
        if hdr:
            body = full
        else:
            body = split_header(full)[1]
        text = base64.b64encode(body).decode("ascii")
        stamp = stamp_of(body)
        n, caps = _plan(len(text), case, sent, place, stamp, step, len(body),
                        hdr, dev, packet_parts)
        total = len(text) + sum(
            _tag(k, n, case, sent, place, stamp, step, len(body), hdr, dev,
                 k == n)[1] for k in range(1, n + 1))
        if total <= budget:
            pick = (step, w, h, body, text, stamp, n, caps)
            break
    if pick is None:  # nothing fits: still send the smallest, the join will judge
        step = len(SIZE_LADDER) - 1
        w, h = SIZE_LADDER[step]
        full = encode_jpeg(win, w, h, quality)
        body = full if hdr else split_header(full)[1]
        text = base64.b64encode(body).decode("ascii")
        stamp = stamp_of(body)
        n, caps = _plan(len(text), case, sent, place, stamp, step, len(body),
                        hdr, dev, packet_parts)
        pick = (step, w, h, body, text, stamp, n, caps)
    step, w, h, body, text, stamp, n, caps = pick

    check = check_of(body)
    packets = []
    at = 0
    for k in range(1, n + 1):
        head, _ = _tag(k, n, case, sent, place, stamp, step, len(body), hdr,
                       dev, k == n)
        piece = text[at:at + caps[k - 1]]
        at += len(piece)
        tail = ":" + check if k == n else ""
        packets.append(head + piece + tail)
    assert at == len(text), "packet plan left payload out"
    parts = sum((len(p) + PART_LEN - 1) // PART_LEN for p in packets)
    return {"packets": packets, "w": w, "h": h, "step": step,
            "size": len(body), "parts": parts, "n": n, "hdr": hdr,
            "dev": dev, "stamp": stamp, "check": check, "sent": sent,
            "place": place, "case": str(case)}


def parse_packet(text):
    """Read one P: packet. None when it is not a good one."""
    if not isinstance(text, str) or not text.startswith("P:"):
        return None
    bits = text.split(":")
    if len(bits) not in (11, 12):
        return None
    (_, case, sent, place, stamp, kn, step, size, hdr, dev, payload) = bits[:11]
    check = bits[11] if len(bits) == 12 else None
    try:
        k, n = kn.split("/")
        k, n, sent, place, step, size, hdr = (int(k), int(n), int(sent),
                                              int(place), int(step), int(size), int(hdr))
    except ValueError:
        return None
    if not (1 <= k <= n and sent >= 1 and place >= 1 and size >= 0
            and hdr in (0, 1) and payload):
        return None
    if (k == n) != (check is not None):
        return None
    ok = set(B64 + "=")
    if (any(c not in ok for c in payload)
            or (check is not None and (len(check) != 6
                                       or any(c not in B64 for c in check)))):
        return None
    return {"case": case, "sent": sent, "place": place, "stamp": stamp,
            "k": k, "n": n, "step": step, "size": size, "hdr": hdr,
            "dev": dev, "payload": payload, "check": check}


def cut_case(images, case, dev="--", hdr=0, packet_parts=None, quality=None):
    """Cut every photo of one case. More photos than the cap: only the first ones go, and `sent` says how many."""
    images = list(images)[:max_photos()]
    return [cut_photo(im, case, len(images), i, dev, hdr, packet_parts, quality)
            for i, im in enumerate(images, 1)]
