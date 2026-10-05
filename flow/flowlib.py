"""Small helper to write Excalidraw flow charts from code, and to check them.

Used by build_flows.py. No outside package is needed.
"""
import json
import random

FS = 20                    # font size in boxes
LINE = 1.25                # line height
PAD_X, PAD_Y = 18, 16      # room around the text in a box

# layer -> (line colour, fill colour)
STYLE = {
    "base":  ("#1e1e1e", "#ffffff"),   # the owner's own boxes
    "add":   ("#e8590c", "#fff4e6"),   # loops closed + edge cases
    "barge": ("#1971c2", "#e7f5ff"),   # cut-in
    "keys":  ("#2f9e44", "#ebfbee"),   # keys
    "end":   ("#e03131", "#ffe3e3"),   # the call ends
}

_WIDE = set("mwMW@%")
_THIN = set("iljtfI.,:;'|!()[]\" ")


def char_w(ch, fs):
    """A safe (a bit wide) guess of one letter's width in the hand font."""
    if ch in _THIN:
        return fs * 0.34
    if ch in _WIDE:
        return fs * 0.86
    if ch.isupper() or ch.isdigit():
        return fs * 0.68
    return fs * 0.55


def text_w(s, fs):
    return sum(char_w(c, fs) for c in s)


def wrap(text, max_w, fs):
    """Break text into lines no wider than max_w. Keeps the writer's own line breaks."""
    out = []
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        for w in words:
            trial = w if not line else line + " " + w
            if text_w(trial, fs) <= max_w or not line:
                line = trial
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


class Node:
    def __init__(self, nid, kind, layer, text, cx, cy, w, h, lines, fs, align):
        self.id, self.kind, self.layer, self.text = nid, kind, layer, text
        self.cx, self.cy, self.w, self.h = cx, cy, w, h
        self.lines, self.fs, self.align = lines, fs, align

    left = property(lambda s: s.cx - s.w / 2)
    right = property(lambda s: s.cx + s.w / 2)
    top = property(lambda s: s.cy - s.h / 2)
    bottom = property(lambda s: s.cy + s.h / 2)

    def fy(self, frac):
        """y at a part of the way down the box."""
        return self.top + self.h * frac

    def fx(self, frac):
        return self.left + self.w * frac

    def anchor(self, side, frac=0.5, gap=0):
        if self.kind == "diamond":
            frac = 0.5
        if side == "l":
            return (self.left - gap, self.fy(frac))
        if side == "r":
            return (self.right + gap, self.fy(frac))
        if side == "t":
            return (self.fx(frac), self.top - gap)
        return (self.fx(frac), self.bottom + gap)

    def rect(self, m=0):
        return (self.left - m, self.top - m, self.right + m, self.bottom + m)


class Edge:
    def __init__(self, src, dst, pts, layer, both, dashed):
        self.src, self.dst, self.pts = src, dst, pts
        self.layer, self.both, self.dashed = layer, both, dashed


class Label:
    def __init__(self, text, cx, cy, layer, fs, lines):
        self.text, self.cx, self.cy, self.layer, self.fs, self.lines = text, cx, cy, layer, fs, lines
        self.w = max(text_w(l, fs) for l in lines)
        self.h = len(lines) * fs * LINE

    def rect(self, m=0):
        return (self.cx - self.w / 2 - m, self.cy - self.h / 2 - m,
                self.cx + self.w / 2 + m, self.cy + self.h / 2 + m)


class Chart:
    def __init__(self, title):
        self.title = title
        self.nodes, self.edges, self.labels = {}, [], []

    # ---- building -------------------------------------------------------
    def node(self, nid, text, cx, cy=None, top=None, w=440, kind="box", layer="base",
             fs=FS, align="center"):
        if kind == "diamond":
            lines = wrap(text, w, fs)
            tw = max(text_w(l, fs) for l in lines)
            th = len(lines) * fs * LINE
            bw, bh = 2 * tw + 44, 2 * th + 44
        else:
            lines = wrap(text, w - 2 * PAD_X, fs)
            th = len(lines) * fs * LINE
            bw, bh = w, th + 2 * PAD_Y
            if kind == "event":
                bh += 26
        if cy is None:
            cy = top + bh / 2
        n = Node(nid, kind, layer, text, cx, cy, bw, bh, lines, fs, align)
        assert nid not in self.nodes, nid
        self.nodes[nid] = n
        return n

    def arrow(self, src, s, dst, d, via=(), layer="add", label=None, lab=None,
              both=False, dashed=False, lw=230):
        """s and d are 'l' 'r' 't' 'b', or ('l', frac). via is a list of ('x', v) / ('y', v) turns.
        lab = (which part of the line, how far along it, dx, dy) places the label."""
        a, b = self.nodes[src], self.nodes[dst]
        s_side, s_fr = (s, 0.5) if isinstance(s, str) else s
        d_side, d_fr = (d, 0.5) if isinstance(d, str) else d
        p0 = a.anchor(s_side, s_fr, gap=3)
        pe = b.anchor(d_side, d_fr, gap=7)
        pts = [p0]
        for kind, v in via:
            x, y = pts[-1]
            pts.append((v, y) if kind == "x" else (x, v))
        x, y = pts[-1]
        if abs(x - pe[0]) > 0.5 and abs(y - pe[1]) > 0.5:
            pts.append((x, pe[1]) if d_side in "lr" else (pe[0], y))
        pts.append(pe)
        clean = [pts[0]]
        for p in pts[1:]:
            if abs(p[0] - clean[-1][0]) > 0.5 or abs(p[1] - clean[-1][1]) > 0.5:
                clean.append(p)
        e = Edge(src, dst, clean, layer, both, dashed)
        e.s_side, e.d_side = s_side, d_side
        self.edges.append(e)
        if label:
            seg, fr, dx, dy = lab if lab else (0, 0.5, 0, 0)
            (x1, y1), (x2, y2) = clean[seg], clean[seg + 1]
            lines = wrap(label, lw, 16)
            lb = Label(label, 0, 0, layer, 16, lines)
            mx, my = x1 + (x2 - x1) * fr, y1 + (y2 - y1) * fr
            if lab is None or (dx == 0 and dy == 0):
                if abs(y1 - y2) < 0.5:
                    dy = -(lb.h / 2 + 8)
                else:
                    dx = lb.w / 2 + 12
            lb.cx, lb.cy = mx + dx, my + dy
            self.labels.append(lb)
        return e

    def note(self, text, cx, cy, layer="add", fs=16, w=260):
        lines = wrap(text, w, fs)
        self.labels.append(Label(text, cx, cy, layer, fs, lines))

    # ---- checks ---------------------------------------------------------
    def check(self):
        errs, warns = [], []
        ns = list(self.nodes.values())
        for i, a in enumerate(ns):
            for b in ns[i + 1:]:
                if _rects_hit(a.rect(12), b.rect(12)):
                    errs.append(f"boxes too close: {a.id} / {b.id}")
        segs = []
        for ei, e in enumerate(self.edges):
            for (x1, y1), (x2, y2) in zip(e.pts, e.pts[1:]):
                if abs(x1 - x2) > 0.5 and abs(y1 - y2) > 0.5:
                    errs.append(f"slanted line: {e.src}->{e.dst}")
                segs.append((ei, x1, y1, x2, y2))
                for n in ns:
                    m = -4 if n.id in (e.src, e.dst) else 10
                    if _seg_hits_rect(x1, y1, x2, y2, n.rect(m)):
                        errs.append(f"line {e.src}->{e.dst} runs through box {n.id}")
            # the line must leave and enter on the named sides
            (x1, y1), (x2, y2) = e.pts[0], e.pts[1]
            want = {"l": x2 < x1, "r": x2 > x1, "t": y2 < y1, "b": y2 > y1}[e.s_side]
            if not want:
                errs.append(f"line {e.src}->{e.dst} leaves the wrong way")
            (x1, y1), (x2, y2) = e.pts[-2], e.pts[-1]
            want = {"l": x2 > x1, "r": x2 < x1, "t": y2 > y1, "b": y2 < y1}[e.d_side]
            if not want:
                errs.append(f"line {e.src}->{e.dst} enters the wrong way")
        crossings = 0
        for i, (ei, ax1, ay1, ax2, ay2) in enumerate(segs):
            for (ej, bx1, by1, bx2, by2) in segs[i + 1:]:
                if ei == ej:
                    continue
                kind = _seg_seg(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2)
                if kind == "overlap":
                    a, b = self.edges[ei], self.edges[ej]
                    errs.append(f"lines lie on each other: {a.src}->{a.dst} / {b.src}->{b.dst}")
                elif kind == "cross":
                    a, b = self.edges[ei], self.edges[ej]
                    crossings += 1
                    warns.append(f"lines cross: {a.src}->{a.dst} / {b.src}->{b.dst}")
        for i, lb in enumerate(self.labels):
            for n in ns:
                if _rects_hit(lb.rect(2), n.rect(2)):
                    errs.append(f"label '{lb.text[:30]}' sits on box {n.id}")
            for other in self.labels[i + 1:]:
                if _rects_hit(lb.rect(2), other.rect(2)):
                    errs.append(f"labels on each other: '{lb.text[:25]}' / '{other.text[:25]}'")
            for (ei, x1, y1, x2, y2) in segs:
                if _seg_hits_rect(x1, y1, x2, y2, lb.rect(1)):
                    e = self.edges[ei]
                    errs.append(f"line {e.src}->{e.dst} runs through label '{lb.text[:30]}'")
        # the flow itself: every box has a way in and a way out, every loop is closed
        outs = {n.id: set() for n in ns}
        ins = {n.id: set() for n in ns}
        for e in self.edges:
            outs[e.src].add(e.dst)
            ins[e.dst].add(e.src)
            if e.both:
                outs[e.dst].add(e.src)
                ins[e.src].add(e.dst)
        for n in ns:
            if n.kind == "note":
                continue
            if n.kind not in ("start", "event") and not ins[n.id]:
                errs.append(f"no way in: {n.id}")
            if n.kind not in ("end", "link") and not outs[n.id]:
                errs.append(f"no way out (dead end): {n.id}")
            if n.kind == "diamond" and len(outs[n.id]) < 2:
                errs.append(f"a choice with one way out: {n.id}")
        starts = [n.id for n in ns if n.kind in ("start", "event")]
        seen = _reach(starts, outs)
        for n in ns:
            if n.kind != "note" and n.id not in seen:
                errs.append(f"can not be reached from the start: {n.id}")
        ends = [n.id for n in ns if n.kind in ("end", "link")]
        can_end = _reach(ends, ins)
        for n in ns:
            if n.kind != "note" and n.id not in can_end:
                errs.append(f"no path to an end of the call: {n.id}")
        return errs, warns, crossings

    def bounds(self):
        xs, ys = [], []
        for n in self.nodes.values():
            xs += [n.left, n.right]
            ys += [n.top, n.bottom]
        for e in self.edges:
            xs += [p[0] for p in e.pts]
            ys += [p[1] for p in e.pts]
        for lb in self.labels:
            r = lb.rect()
            xs += [r[0], r[2]]
            ys += [r[1], r[3]]
        return min(xs), min(ys), max(xs), max(ys)

    # ---- Excalidraw file --------------------------------------------------
    def excalidraw(self):
        rnd = random.Random(7)
        els = []

        def base(eid, typ, x, y, w, h, stroke, bg, **kw):
            d = {
                "id": eid, "type": typ, "x": round(x, 1), "y": round(y, 1),
                "width": round(w, 1), "height": round(h, 1), "angle": 0,
                "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
                "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
                "groupIds": [], "frameId": None, "roundness": None,
                "seed": rnd.randint(1, 2 ** 31), "version": 1,
                "versionNonce": rnd.randint(1, 2 ** 31), "isDeleted": False,
                "boundElements": [], "updated": 1759650000000, "link": None, "locked": False,
            }
            d.update(kw)
            return d

        def text_el(eid, x, y, lines, fs, colour, original, container=None, align="center"):
            w = max(text_w(l, fs) for l in lines)
            h = len(lines) * fs * LINE
            return base(eid, "text", x, y, w, h, colour, "transparent",
                        strokeWidth=1, text="\n".join(lines), fontSize=fs, fontFamily=1,
                        textAlign=align, verticalAlign="middle" if container else "top",
                        containerId=container, originalText=original, lineHeight=LINE,
                        autoResize=True)

        by_id = {}
        for n in self.nodes.values():
            stroke, bg = STYLE["end" if n.kind == "end" else n.layer]
            typ = {"diamond": "diamond", "event": "ellipse"}.get(n.kind, "rectangle")
            el = base("n_" + n.id, typ, n.left, n.top, n.w, n.h, stroke, bg)
            if typ == "rectangle":
                el["roundness"] = {"type": 3}
            elif typ == "diamond":
                el["roundness"] = {"type": 2}
            if n.kind == "note":
                el["strokeStyle"] = "dashed"
                el["strokeWidth"] = 1
            if n.kind in ("start", "end", "link"):
                el["strokeWidth"] = 4
            tw = max(text_w(l, n.fs) for l in n.lines)
            th = len(n.lines) * n.fs * LINE
            tx = n.left + PAD_X if n.align == "left" and n.kind != "diamond" else n.cx - tw / 2
            t = text_el("t_" + n.id, tx, n.cy - th / 2, n.lines, n.fs, "#1e1e1e", n.text,
                        container="n_" + n.id, align=n.align if n.kind != "diamond" else "center")
            el["boundElements"].append({"type": "text", "id": t["id"]})
            els += [el, t]
            by_id[n.id] = el
        for i, e in enumerate(self.edges):
            stroke = STYLE[e.layer][0]
            x0, y0 = e.pts[0]
            rel = [[round(x - x0, 1), round(y - y0, 1)] for x, y in e.pts]
            xs, ys = [p[0] for p in rel], [p[1] for p in rel]
            el = base(f"a_{i}", "arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys),
                      stroke, "transparent", points=rel, lastCommittedPoint=None,
                      startBinding={"elementId": "n_" + e.src, "focus": 0, "gap": 3},
                      endBinding={"elementId": "n_" + e.dst, "focus": 0, "gap": 7},
                      startArrowhead="arrow" if e.both else None, endArrowhead="arrow",
                      elbowed=False)
            if e.dashed:
                el["strokeStyle"] = "dashed"
            by_id[e.src]["boundElements"].append({"type": "arrow", "id": el["id"]})
            if e.dst != e.src:
                by_id[e.dst]["boundElements"].append({"type": "arrow", "id": el["id"]})
            els.append(el)
        for i, lb in enumerate(self.labels):
            r = lb.rect()
            colour = STYLE[lb.layer][0]
            els.append(text_el(f"l_{i}", r[0], r[1], lb.lines, lb.fs, colour, lb.text))
        return {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
                "elements": els,
                "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
                "files": {}}

    # ---- a plain picture, to look at the layout ----------------------------
    def svg(self):
        x0, y0, x1, y1 = self.bounds()
        m = 40
        W, H = x1 - x0 + 2 * m, y1 - y0 + 2 * m
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
             f'viewBox="{x0 - m:.0f} {y0 - m:.0f} {W:.0f} {H:.0f}">',
             f'<rect x="{x0 - m}" y="{y0 - m}" width="{W}" height="{H}" fill="#ffffff"/>',
             '<defs>']
        for layer, (stroke, _) in STYLE.items():
            o.append(f'<marker id="h_{layer}" markerWidth="12" markerHeight="12" refX="9" refY="6" '
                     f'orient="auto-start-reverse"><path d="M1,1 L10,6 L1,11" fill="none" '
                     f'stroke="{stroke}" stroke-width="2"/></marker>')
        o.append('</defs>')
        for e in self.edges:
            stroke = STYLE[e.layer][0]
            d = " ".join(f"{x:.1f},{y:.1f}" for x, y in e.pts)
            extra = f' marker-start="url(#h_{e.layer})"' if e.both else ""
            dash = ' stroke-dasharray="8 6"' if e.dashed else ""
            o.append(f'<polyline points="{d}" fill="none" stroke="{stroke}" stroke-width="2"{dash} '
                     f'marker-end="url(#h_{e.layer})"{extra}/>')
        for n in self.nodes.values():
            stroke, bg = STYLE["end" if n.kind == "end" else n.layer]
            sw = 4 if n.kind in ("start", "end", "link") else 2
            dash = ' stroke-dasharray="7 5"' if n.kind == "note" else ""
            if n.kind == "diamond":
                p = f"{n.cx},{n.top} {n.right},{n.cy} {n.cx},{n.bottom} {n.left},{n.cy}"
                o.append(f'<polygon points="{p}" fill="{bg}" stroke="{stroke}" stroke-width="{sw}"/>')
            elif n.kind == "event":
                o.append(f'<ellipse cx="{n.cx}" cy="{n.cy}" rx="{n.w / 2}" ry="{n.h / 2}" fill="{bg}" '
                         f'stroke="{stroke}" stroke-width="{sw}"/>')
            else:
                o.append(f'<rect x="{n.left}" y="{n.top}" width="{n.w}" height="{n.h}" rx="14" '
                         f'fill="{bg}" stroke="{stroke}" stroke-width="{sw}"{dash}/>')
            th = len(n.lines) * n.fs * LINE
            for i, line in enumerate(n.lines):
                ty = n.cy - th / 2 + (i + 0.78) * n.fs * LINE
                if n.align == "left" and n.kind != "diamond":
                    o.append(f'<text x="{n.left + PAD_X}" y="{ty:.1f}" font-size="{n.fs}" '
                             f'font-family="Chalkboard SE, Comic Sans MS, sans-serif">{_esc(line)}</text>')
                else:
                    o.append(f'<text x="{n.cx}" y="{ty:.1f}" font-size="{n.fs}" text-anchor="middle" '
                             f'font-family="Chalkboard SE, Comic Sans MS, sans-serif">{_esc(line)}</text>')
        for lb in self.labels:
            colour = STYLE[lb.layer][0]
            for i, line in enumerate(lb.lines):
                ty = lb.cy - lb.h / 2 + (i + 0.78) * lb.fs * LINE
                o.append(f'<text x="{lb.cx}" y="{ty:.1f}" font-size="{lb.fs}" text-anchor="middle" '
                         f'fill="{colour}" font-family="Chalkboard SE, Comic Sans MS, sans-serif">'
                         f'{_esc(line)}</text>')
        o.append('</svg>')
        return "\n".join(o)


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rects_hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _seg_hits_rect(x1, y1, x2, y2, r):
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    return lo_x < r[2] and hi_x > r[0] and lo_y < r[3] and hi_y > r[1]


def _seg_seg(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    a_h, b_h = abs(ay1 - ay2) < 0.5, abs(by1 - by2) < 0.5
    if a_h and b_h:
        if abs(ay1 - by1) < 6:
            lo, hi = max(min(ax1, ax2), min(bx1, bx2)), min(max(ax1, ax2), max(bx1, bx2))
            return "overlap" if hi - lo > 6 else None
        return None
    if not a_h and not b_h:
        if abs(ax1 - bx1) < 6:
            lo, hi = max(min(ay1, ay2), min(by1, by2)), min(max(ay1, ay2), max(by1, by2))
            return "overlap" if hi - lo > 6 else None
        return None
    if not a_h:
        ax1, ay1, ax2, ay2, bx1, by1, bx2, by2 = bx1, by1, bx2, by2, ax1, ay1, ax2, ay2
    # a is flat, b is upright
    if min(ax1, ax2) + 1 < bx1 < max(ax1, ax2) - 1 and min(by1, by2) + 1 < ay1 < max(by1, by2) - 1:
        return "cross"
    return None


def _reach(starts, graph):
    seen, todo = set(starts), list(starts)
    while todo:
        for nxt in graph[todo.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def check_file(path):
    """Read a written .excalidraw file back and check what Excalidraw itself needs."""
    errs = []
    with open(path) as f:
        doc = json.load(f)
    els = doc["elements"]
    ids = [e["id"] for e in els]
    if len(ids) != len(set(ids)):
        errs.append("two parts share an id")
    by = {e["id"]: e for e in els}
    for e in els:
        if e["type"] == "text" and e.get("containerId"):
            box = by.get(e["containerId"])
            if not box or {"type": "text", "id": e["id"]} not in box["boundElements"]:
                errs.append(f"text {e['id']} is not tied to its box")
        if e["type"] == "arrow":
            for end in ("startBinding", "endBinding"):
                b = e.get(end)
                box = by.get(b["elementId"]) if b else None
                if not box:
                    errs.append(f"arrow {e['id']} has a loose end ({end})")
                elif {"type": "arrow", "id": e["id"]} not in box["boundElements"]:
                    errs.append(f"box {box['id']} does not know arrow {e['id']}")
    counts = {}
    for e in els:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    return errs, counts
