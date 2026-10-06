"""Cut photos into P: packets for sending by SMS. Plain words.

Run: .venv/bin/python -m tools.sms_cut photo p1.jpg [p2.jpg ...]
Prints for each photo: size, bytes, parts, packets. Writes a contact sheet.
"""

import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from haqdaar.keypad_sms.pack import SIZE_LADDER, cut_photo  # noqa: E402


def main(argv):
    if len(argv) < 3 or argv[1] != "photo":
        print("use: sms_cut photo p1.jpg [p2.jpg ...] [--case NAME] [--dev DD] [--hdr 0|1]")
        return 2
    paths, case, dev, hdr = [], "demo1", "--", 0
    it = iter(argv[2:])
    for a in it:
        if a == "--case":
            case = next(it)
        elif a == "--dev":
            dev = next(it)
        elif a == "--hdr":
            hdr = int(next(it))
        else:
            paths.append(a)
    if not paths:
        print("no photos given")
        return 2
    sent = len(paths)
    smalls = []
    for i, path in enumerate(paths, 1):
        cut = cut_photo(path, case, sent, i, dev=dev, hdr=hdr)
        print("%s: %dx%d step %d, %d bytes, %d parts, %d packets" % (
            path, cut["w"], cut["h"], cut["step"], cut["size"],
            cut["parts"], cut["n"]))
        img = Image.open(path).convert("RGB")
        smalls.append(img.resize((cut["w"], cut["h"]), Image.BICUBIC))
    sheet_w = sum(s.width for s in smalls) + 10 * (len(smalls) - 1)
    sheet_h = max(s.height for s in smalls)
    sheet = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
    x = 0
    for s in smalls:
        sheet.paste(s, (x, 0))
        x += s.width + 10
    sheet.save("sms_sheet.jpg", "JPEG", quality=90)
    print("sheet: sms_sheet.jpg (%dx%d)" % (sheet_w, sheet_h))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
