"""Draw Reviewer 2, the tiger mosquito, as an SVG illustration (and a PNG preview).

python3 draw_reviewer2.py [out.svg] [preview.png]
"""
import math
import sys

INK = "#16181d"
BODY_D = "#1b1d23"
BODY_L = "#4a4f5c"
WHITE = "#f4f1ea"
RED = "#d2232a"
RED_D = "#8e0f14"


SEG_W = [(10.5, 7.0), (6.5, 5.0), (4.2, 2.4)]


def leg(points, w0=8.5, w1=2.6, rings=4, shadow=True, fill=BODY_D, stroke=INK, sheen=0.55):
    """A jointed mosquito leg: tapered segments, white rings on the last segment, a shadow at the foot."""
    s = ""
    n = len(points) - 1
    for i in range(n):
        (x0, y0), (x1, y1) = points[i], points[i + 1]
        wa, wb = SEG_W[min(i, 2)] if n == 3 else (w0 + (w1 - w0) * i / n, w0 + (w1 - w0) * (i + 1) / n)
        if n == 3:
            wa, wb = wa * w0 / 8.5, wb * w0 / 8.5
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        if nx * -0.6 + ny * -0.8 < 0:  # the sheen faces the key light (upper left)
            nx, ny = -nx, -ny
        poly = [(x0 + nx * wa / 2, y0 + ny * wa / 2), (x1 + nx * wb / 2, y1 + ny * wb / 2),
                (x1 - nx * wb / 2, y1 - ny * wb / 2), (x0 - nx * wa / 2, y0 - ny * wa / 2)]
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in poly) + " Z"
        sw = 2 if i < n - 1 else 1.2
        s += f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"/>'
        # sheen along the segment
        s += (f'<path d="M{x0 + nx * wa * 0.2:.1f} {y0 + ny * wa * 0.2:.1f} L{x1 + nx * wb * 0.2:.1f} {y1 + ny * wb * 0.2:.1f}" '
              f'stroke="#8d93a3" stroke-opacity="{sheen}" stroke-width="{max(wb * 0.25, 0.8):.1f}" stroke-linecap="round"/>')
        if i >= n - 2:  # white rings at the base of the tarsal segments
            k = rings if i == n - 1 else 0
            for j in range(k):
                tt = (0.02, 0.34, 0.60, 0.80)[j] if k == 4 else 0.12 + 0.8 * j / max(k, 1)
                cx, cy = x0 + dx * tt, y0 + dy * tt
                ww = wa + (wb - wa) * tt + 1
                s += (f'<path d="M{cx + nx * ww / 2:.1f} {cy + ny * ww / 2:.1f} L{cx + dx / L * 3.5 + nx * ww / 2:.1f} {cy + dy / L * 3.5 + ny * ww / 2:.1f} '
                      f'L{cx + dx / L * 3.5 - nx * ww / 2:.1f} {cy + dy / L * 3.5 - ny * ww / 2:.1f} L{cx - nx * ww / 2:.1f} {cy - ny * ww / 2:.1f} Z" fill="{WHITE}"/>')
    for k, (x, y) in enumerate(points[1:-1]):  # knees, barely wider than the segments
        wa = SEG_W[min(k, 2)][1] * w0 / 8.5 if n == 3 else w0 + (w1 - w0) * (k + 1) / n
        s += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{wa / 2 + 0.6:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
    fx, fy = points[-1]
    if shadow:  # claws on planted feet
        cl, cw = (4, 1.2) if fill == BODY_D else (3, 1.0)
        s += (f'<path d="M{fx:.1f} {fy:.1f} l-{cl} 1.5 M{fx:.1f} {fy:.1f} l{cl} 1.5" stroke="{stroke}" stroke-width="{cw}" '
              'stroke-linecap="round" fill="none"/>')
    elif n == 3:
        (ax, ay), (bx, by) = points[-2], points[-1]
        L = math.hypot(bx - ax, by - ay) or 1
        s += (f'<path d="M{bx:.1f} {by:.1f} l{3 * (bx - ax) / L:.1f} {3 * (by - ay) / L:.1f}" stroke="{INK}" '
              'stroke-width="1.2" stroke-linecap="round"/>')
    if shadow:
        s = (f'<ellipse cx="{fx + 2:.1f}" cy="{fy + 2:.1f}" rx="10" ry="3" fill="#000" opacity="0.22"/>'
             f'<ellipse cx="{fx + 0.5:.1f}" cy="{fy + 1:.1f}" rx="4" ry="1.5" fill="#000" opacity="0.45"/>') + s
    return s


def plumose(x0, y0, cx, cy, x1, y1, n=16, hair=11, side=1):
    """Feathery antenna: a quadratic curve with short hairs."""
    s = f'<path d="M{x0} {y0} Q{cx} {cy} {x1} {y1}" stroke="{INK}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    s += (f'<path d="M{x0 - 1} {y0 - 1} Q{cx - 1} {cy - 1} {x1 - 1} {y1 - 1}" stroke="#8d93a3" stroke-opacity="0.4" '
          'stroke-width="1" fill="none" stroke-linecap="round"/>')
    for i in range(2, n):
        t = i / n
        x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1
        y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1
        dx = 2 * (1 - t) * (cx - x0) + 2 * t * (x1 - cx)
        dy = 2 * (1 - t) * (cy - y0) + 2 * t * (y1 - cy)
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        h = hair * (1 - 0.6 * t)
        for sgn in (1, -1):
            s += (f'<path d="M{x:.1f} {y:.1f} l{(sgn * nx * h + dx / L * 3):.1f} {(sgn * ny * h + dy / L * 3):.1f}" '
                  f'stroke="{INK}" stroke-width="1.2" stroke-linecap="round"/>')
    return s


def paper_lines(x, y, w, n, gap=13, seed=0):
    out = []
    for i in range(n):
        lw = w * (0.55 + 0.45 * ((i * 37 + seed * 11) % 10) / 10) if i % 5 == 4 else w
        out.append(f'<rect x="{x}" y="{y + i * gap}" width="{lw:.0f}" height="4" rx="2" fill="#b9b4a8"/>')
    return "".join(out)


def reject_stamp(cx, cy, w, h=None, font=None, stroke=None, ls=None, angle=-14, rx=None, base=None, pivot=None):
    """The REJECT rubber-stamp imprint used on every rejected paper: a rounded red box with REJECT
    in bold DejaVu Sans, rotated by `angle` around its centre. Proportions follow the Turing sheet
    (72 wide); the keyword arguments override them (base: baseline below the centre; pivot: rotation centre)."""
    k = w / 72.0
    h = 22 * k if h is None else h
    font = 14 * k if font is None else font
    stroke = 2.6 * k if stroke is None else stroke
    ls = 1 * k if ls is None else ls
    rx = 3 * k if rx is None else rx
    base = 0.43 * font if base is None else base
    px, py = (cx, cy) if pivot is None else pivot
    return (f'<g transform="rotate({angle:g} {px:g} {py:g})"><rect x="{cx - w / 2:g}" y="{cy - h / 2:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" '
            f'fill="none" stroke="{RED}" stroke-width="{stroke:g}" opacity="0.85"/>'
            f'<text x="{cx:g}" y="{cy + base:g}" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" '
            f'font-size="{font:g}" fill="{RED}" opacity="0.85" letter-spacing="{ls:g}">REJECT</text></g>')


def mug_text(txt, cx, cy, size, bold, R=45.0, tilt=0.244):
    """Text wrapped on the mug's cylinder: letters follow the rim's curve and narrow toward the sides."""
    widths = {" ": 0.32, ".": 0.35, "'": 0.3, "#": 0.84, "I": 0.4}
    adv = [size * widths.get(c, 0.62 if c.isdigit() else 0.74) for c in txt]
    total = sum(adv)
    out, s_ = [], -total / 2
    for c, a in zip(txt, adv):
        th = (s_ + a / 2) / R
        x = cx + R * math.sin(th)
        y = cy + tilt * R * (math.cos(th) - 1)
        w = "700" if bold else "400"
        out.append(f'<text text-anchor="middle" transform="translate({x:.2f} {y:.2f}) scale({math.cos(th):.3f} 1)" '
                   f'font-family="DejaVu Serif, serif" font-weight="{w}" font-size="{size}" fill="{RED}">'
                   f'{"&#39;" if c == chr(39) else c}</text>')
        s_ += a
    return "".join(out)


def svg():
    p = []
    p.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 640" width="900" height="640">')
    p.append('<title>Reviewer 2</title>')
    p.append(f'''<defs>
  <radialGradient id="bg" cx="0.45" cy="0.35" r="0.85">
    <stop offset="0" stop-color="#fdf3df"/><stop offset="0.6" stop-color="#ecd9b8"/><stop offset="1" stop-color="#b99a72"/>
  </radialGradient>
  <linearGradient id="desk" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#8a5a36"/><stop offset="1" stop-color="#5b3820"/>
  </linearGradient>
  <radialGradient id="head" cx="0.35" cy="0.3" r="0.8">
    <stop offset="0" stop-color="#6a7080"/><stop offset="0.55" stop-color="#2c2f38"/><stop offset="1" stop-color="#121318"/>
  </radialGradient>
  <radialGradient id="thorax" cx="0.4" cy="0.3" r="0.8">
    <stop offset="0" stop-color="#5a5f6d"/><stop offset="0.6" stop-color="#23262d"/><stop offset="1" stop-color="#101115"/>
  </radialGradient>
  <linearGradient id="abd" x1="0.3" y1="0" x2="0.6" y2="1">
    <stop offset="0" stop-color="#555a67"/><stop offset="0.5" stop-color="#22252c"/><stop offset="1" stop-color="#0f1014"/>
  </linearGradient>
  <radialGradient id="eye" cx="0.35" cy="0.3" r="0.75">
    <stop offset="0" stop-color="#7d2e2e"/><stop offset="0.6" stop-color="#3a1214"/><stop offset="1" stop-color="#170607"/>
  </radialGradient>
  <linearGradient id="wing" x1="0" y1="0.5" x2="1" y2="0.5">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.15"/><stop offset="0.15" stop-color="#ffffff" stop-opacity="0.7"/><stop offset="0.45" stop-color="#cfe6f7" stop-opacity="0.45"/>
    <stop offset="0.7" stop-color="#e8d4f5" stop-opacity="0.4"/><stop offset="1" stop-color="#ffffff" stop-opacity="0.25"/>
  </linearGradient>
  <linearGradient id="pen" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{RED_D}"/><stop offset="0.35" stop-color="#ff5a5f"/><stop offset="0.6" stop-color="{RED}"/><stop offset="1" stop-color="{RED_D}"/>
  </linearGradient>
  <linearGradient id="metal" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#7d7f86"/><stop offset="0.45" stop-color="#f2f3f5"/><stop offset="1" stop-color="#6b6d74"/>
  </linearGradient>
  <radialGradient id="shadow" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#000" stop-opacity="0.28"/><stop offset="1" stop-color="#000" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="ink" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{RED}" stop-opacity="0.95"/><stop offset="0.7" stop-color="{RED}" stop-opacity="0.8"/><stop offset="1" stop-color="{RED}" stop-opacity="0"/>
  </radialGradient>
  <pattern id="hex" width="7" height="6" patternUnits="userSpaceOnUse">
    <path d="M0 3 L1.75 0 L5.25 0 L7 3 L5.25 6 L1.75 6 Z" fill="none" stroke="#000" stroke-opacity="0.35" stroke-width="0.6"/>
  </pattern>
  <clipPath id="abdclip"><path d="M-118 0 C-118 -30 -70 -40 -10 -38 C50 -36 100 -24 120 -8 C126 -3 126 5 118 10 C96 26 50 34 -10 36 C-70 38 -118 30 -118 0 Z"/></clipPath>
  <linearGradient id="silver" x1="0" y1="0" x2="1" y2="0.4">
    <stop offset="0" stop-color="#c9ced6"/><stop offset="0.35" stop-color="#ffffff"/><stop offset="1" stop-color="#7d838e"/>
  </linearGradient>
  <radialGradient id="vignette" cx="0.5" cy="0.45" r="0.75">
    <stop offset="0.6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#2a1a0c" stop-opacity="0.3"/>
  </radialGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#8a6212"/><stop offset="0.35" stop-color="#ffe07a"/><stop offset="0.6" stop-color="#e0a92a"/><stop offset="1" stop-color="#7a540c"/>
  </linearGradient>
  <linearGradient id="marble" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#3b3f48"/><stop offset="1" stop-color="#1c1e23"/>
  </linearGradient>
  <linearGradient id="mugbody" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#e9e4da"/><stop offset="0.18" stop-color="#ffffff"/><stop offset="0.55" stop-color="#f1ece2"/><stop offset="0.85" stop-color="#cfc8ba"/><stop offset="1" stop-color="#b8b0a1"/>
  </linearGradient>
  <linearGradient id="mughandle" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#ffffff"/><stop offset="0.5" stop-color="#e9e4da"/><stop offset="1" stop-color="#b8b0a1"/>
  </linearGradient>
  <linearGradient id="mugin" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#cfc8ba"/><stop offset="1" stop-color="#f7f4ee"/>
  </linearGradient>
  <linearGradient id="abdshade" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="0.45" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.55"/>
  </linearGradient>
  <linearGradient id="wallao" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#3a2412" stop-opacity="0"/><stop offset="1" stop-color="#3a2412" stop-opacity="0.25"/>
  </linearGradient>
  <linearGradient id="rubber" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{RED}"/><stop offset="1" stop-color="{RED_D}"/>
  </linearGradient>
  <clipPath id="mugclip"><path d="M50 470 L56 552 Q95 566 134 552 L140 470 Z"/></clipPath>
</defs>''')

    # ---- background: wall and wooden desk with grain and knots ----
    p.append('<rect width="900" height="640" fill="url(#bg)"/>')
    p.append('<rect y="470" width="900" height="170" fill="url(#desk)"/>')
    p.append('<rect y="440" width="900" height="30" fill="url(#wallao)"/>')
    p.append('<rect y="468" width="900" height="6" fill="#a8744a"/>')
    p.append('<path d="M0 474.5 L900 474.5" stroke="#3f2614" stroke-width="1" opacity="0.6"/>')
    k = 1
    while True:
        y = 476 + 3 * k ** 1.6
        if y > 640:
            break
        t = (y - 476) / 164
        a = (3 + 6 * t) * (1 + (k % 3) * 0.4)
        p.append(f'<path d="M0 {y:.1f} C150 {y - a:.1f} 260 {y + a:.1f} 420 {y:.1f} S700 {y - a:.1f} 900 {y + a / 2:.1f}" stroke="#3f2614" stroke-opacity="{0.12 + 0.14 * t:.2f}" stroke-width="{1 + 1.5 * t:.1f}" fill="none"/>')
        k += 1
    for kx, ky, ry in ((790, 600, 7), (120, 615, 8)):
        p.append(f'<ellipse cx="{kx}" cy="{ky}" rx="22" ry="{ry}" fill="none" stroke="#3f2614" stroke-opacity="0.35" stroke-width="2"/>')
        p.append(f'<ellipse cx="{kx}" cy="{ky}" rx="9" ry="{ry * 0.42:.1f}" fill="#3f2614" fill-opacity="0.35"/>')
    p.append('<ellipse cx="300" cy="500" rx="300" ry="25" fill="#fff" opacity="0.06"/>')

    # ---- pile of reviews to do ----
    p.append('<ellipse cx="795" cy="470" rx="110" ry="6" fill="url(#shadow)"/>')
    p.append('<g transform="translate(42 0)">')
    p.append('<path d="M655 385 L665 377 L855 377 L845 385 Z" fill="#fbf8f1" stroke="#8d8576" stroke-width="1"/>')
    for i in range(7):
        y = 455 - i * 11
        p.append(f'<rect x="{655 + (i % 2) * 6}" y="{y}" width="190" height="12" rx="2" fill="{"#fbf8f1" if i % 2 else "#efe9dc"}" stroke="#8d8576" stroke-width="1.2"/>')
    p.append('<rect x="700" y="404" width="112" height="26" rx="3" fill="#ffe680" stroke="#8d8576" stroke-width="1.2" transform="rotate(-4 753 417)"/>')
    p.append(f'<text x="756" y="422" text-anchor="middle" HAND font-size="13" fill="{INK}" transform="rotate(-4 753 417)">12 due Friday</text>')
    p.append('<rect x="672" y="436" width="166" height="20" rx="2" fill="#ff9e80" stroke="#8d8576" stroke-width="1.2" transform="rotate(3 755 446)"/>')
    p.append(f'<text x="755" y="450" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="8.5" fill="{INK}" transform="rotate(3 755 446)">Emergency review due yesterday</text>')

    p.append('<rect x="650" y="385" width="202" height="84" rx="6" fill="#dff1ff" fill-opacity="0.18" stroke="#ffffff" stroke-opacity="0.7" stroke-width="2"/>')
    p.append('<path d="M650 381 L662 373 L860 373 L852 385" fill="#dff1ff" fill-opacity="0.18" stroke="#ffffff" stroke-opacity="0.6" stroke-width="1.5"/>')
    p.append('<path d="M652 468.5 L850 468.5" stroke="#5e5446" stroke-width="1" opacity="0.6"/>')
    for x0 in (670, 720, 790):
        p.append(f'<path d="M{x0} 390 L{x0 + 30} 466" stroke="#fff" stroke-opacity="0.55" stroke-width="3"/>')
    p.append('<path d="M656 400 Q656 389 668 389 L760 389" stroke="#fff" stroke-opacity="0.85" stroke-width="3" fill="none" stroke-linecap="round"/>')
    p.append('<path d="M846 420 L846 460" stroke="#fff" stroke-opacity="0.5" stroke-width="2" stroke-linecap="round"/>')
    p.append('</g>')

    # ---- the authors' rebuttal, pinned to the wall, still sealed ----
    p.append('<g transform="rotate(3 505 70)">')
    p.append('<rect x="440" y="30" width="132" height="82" fill="#000" opacity="0.16" transform="translate(3 4)"/>')
    p.append('<rect x="440" y="30" width="132" height="82" rx="2" fill="#f4ead2" stroke="#9c8f72" stroke-width="1.5"/>')
    p.append('<path d="M440 30 L506 76 L572 30" fill="#ece0c2" stroke="#9c8f72" stroke-width="1.5" stroke-linejoin="round"/>')
    p.append('<path d="M440 112 L494 70 M572 112 L518 70" stroke="#9c8f72" stroke-width="1" opacity="0.6"/>')
    p.append(f'<circle cx="506" cy="76" r="8" fill="{RED}" stroke="#7a1015" stroke-width="1.2"/>')
    p.append('<text x="506" y="79.5" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="8" fill="#7a1015">R</text>')
    p.append(f'<text x="506" y="104" text-anchor="middle" HAND font-size="9" fill="{INK}">Authors\' rebuttal</text>')
    p.append(f'<g><rect x="466" y="44" width="80" height="17" rx="3" fill="#f4ead2" fill-opacity="0.6" stroke="{RED}" stroke-width="2.2" opacity="0.9"/>'
             f'<text x="506" y="56.5" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="10" fill="{RED}" opacity="0.9">Do NOT read!</text></g>')
    # a cobweb in the top corner: it has been there a while
    p.append('<path d="M572 30 L548 30 M572 30 L572 52 M572 30 L553 47 M556 30 Q560 36 572 37 M562 30 Q565 41 572 45 M551 30 Q556 42 572 49" stroke="#8a8a8a" stroke-width="0.7" fill="none" opacity="0.8"/>')
    p.append(f'<circle cx="506" cy="34" r="4.5" fill="{RED}" stroke="#7a1015" stroke-width="1"/>')
    p.append('</g>')

    # ---- UFO poster: I want to believe (that it is novel) ----
    p.append('<rect x="596" y="16" width="150" height="96" fill="#000" opacity="0.18" transform="translate(4 5)"/>')
    p.append('<rect x="596" y="16" width="150" height="96" fill="#0d1014" stroke="#2b2d36" stroke-width="2"/>')
    p.append('<rect x="602" y="22" width="138" height="62" fill="#1b2633"/>')
    for sx, sy in ((612, 30), (640, 27), (700, 33), (728, 28), (622, 46), (716, 50)):
        p.append(f'<circle cx="{sx}" cy="{sy}" r="0.9" fill="#fff" opacity="0.8"/>')
    p.append('<path d="M660 44 L644 84 L700 84 L684 44 Z" fill="#fff6c8" opacity="0.28"/>')
    p.append('<ellipse cx="672" cy="42" rx="20" ry="5" fill="#9aa3ad" stroke="#d9dee4" stroke-width="1"/>')
    p.append('<path d="M662 40 Q672 30 682 40 Z" fill="#c4ccd4"/>')
    for k in range(10):
        x0 = 602 + k * 14
        h = 12 + (k * 7) % 9
        p.append(f'<path d="M{x0} 84 L{x0 + 7} {84 - h} L{x0 + 14} 84 Z" fill="#0a0d10"/>')
    p.append('<text x="671" y="98" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="10.5" fill="#fff" letter-spacing="1.5">I WANT TO BELIEVE</text>')
    p.append('<text x="671" y="108" text-anchor="middle" font-family="DejaVu Serif, serif" font-style="italic" font-size="7" fill="#ddd">...that there is lack of novelty</text>')

    # ---- today's agenda on the wall ----
    p.append('<g transform="rotate(3 845 240)">')
    p.append('<rect x="800" y="176" width="92" height="120" fill="#000" opacity="0.15" transform="translate(3 4)"/>')
    p.append('<rect x="800" y="176" width="92" height="120" fill="#fffdf7" stroke="#9c9484" stroke-width="1.5"/>')
    p.append(f'<rect x="800" y="176" width="92" height="18" fill="{RED}"/>')
    p.append('<text x="846" y="189" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="9" fill="#fff">TODAY</text>')
    rows = (("12:55", "12 reviews", "(5 min)"), ("13:00", "Lunch", "(2 h)"), ("15:00", "Complain about", "reviewers"))
    for k, (h, a1, a2) in enumerate(rows):
        y = 208 + k * 30
        p.append(f'<text x="806" y="{y}" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="7" fill="#555">{h}</text>')
        p.append(f'<text x="834" y="{y}" font-family="DejaVu Sans, sans-serif" font-size="6.5" fill="{INK}">{a1}</text>')
        p.append(f'<text x="834" y="{y + 9}" font-family="DejaVu Sans, sans-serif" font-size="6.5" fill="{INK}">{a2}</text>')
        p.append(f'<path d="M804 {y + 15} L888 {y + 15}" stroke="#ddd" stroke-width="1"/>')
    p.append('</g>')

    # ---- Turing 1936, pinned on the wall: rejected, with a sticky note ----
    p.append('<g transform="rotate(-4 238 110)">')
    p.append('<rect x="188" y="40" width="102" height="134" fill="#000" opacity="0.16" transform="translate(3 4)"/>')
    p.append('<rect x="188" y="40" width="102" height="134" fill="#fffdf7" stroke="#9c9484" stroke-width="1.5"/>')
    p.append(f'<text x="239" y="60" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="8.2" fill="{INK}">On Computable</text>')
    p.append(f'<text x="239" y="70" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="8.2" fill="{INK}">Numbers</text>')
    p.append('<text x="239" y="81" text-anchor="middle" font-family="DejaVu Serif, serif" font-style="italic" font-size="6" fill="#555">A. M. Turing, 1936</text>')
    p.append(paper_lines(198, 90, 82, 6, gap=9, seed=7))
    p.append(reject_stamp(239, 121, 72, base=6, pivot=(239, 122)))
    p.append(f'<circle cx="239" cy="44" r="4.5" fill="{RED}" stroke="#7a1015" stroke-width="1"/>')
    p.append('</g>')
    p.append('<g transform="rotate(6 262 168)">')
    p.append('<rect x="226" y="146" width="80" height="42" fill="#000" opacity="0.15" transform="translate(2 3)"/>')
    p.append('<rect x="226" y="146" width="80" height="42" fill="#ffe680" stroke="#c9b24a" stroke-width="1"/>')
    p.append(f'<text x="266" y="163" text-anchor="middle" HAND font-weight="700" font-size="9" fill="{INK}">no practical</text>')
    p.append(f'<text x="266" y="177" text-anchor="middle" HAND font-weight="700" font-size="9" fill="{INK}">applications</text>')
    p.append('</g>')

    # ---- Shannon 1948, pinned on the wall beside Turing: too compressed, with a sticky note ----
    p.append('<g transform="rotate(2 818 92)">')
    p.append('<rect x="766" y="30" width="104" height="124" fill="#000" opacity="0.16" transform="translate(3 4)"/>')
    p.append('<rect x="766" y="30" width="104" height="124" fill="#fffdf7" stroke="#9c9484" stroke-width="1.5"/>')
    p.append(f'<text x="818" y="50" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="6.8" fill="{INK}">A Mathematical Theory</text>')
    p.append(f'<text x="818" y="60" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="6.8" fill="{INK}">of Communication</text>')
    p.append('<text x="818" y="71" text-anchor="middle" font-family="DejaVu Serif, serif" font-style="italic" font-size="5.6" fill="#555">C. E. Shannon, 1948</text>')
    p.append(paper_lines(778, 80, 80, 6, gap=9, seed=11))
    p.append(f'<circle cx="818" cy="34" r="4.5" fill="{RED}" stroke="#7a1015" stroke-width="1"/>')
    p.append('</g>')
    p.append('<g transform="rotate(-6 833 136)">')
    p.append('<rect x="785" y="122" width="96" height="28" fill="#000" opacity="0.15" transform="translate(2 3)"/>')
    p.append('<rect x="785" y="122" width="96" height="28" fill="#ffe680" stroke="#c9b24a" stroke-width="1"/>')
    p.append(f'<text x="833" y="140" text-anchor="middle" HAND font-weight="700" font-size="8.5" fill="{INK}">too compressed</text>')
    p.append('</g>')

    # ---- Knuth, pinned on the wall like Turing: rejected as incomplete ----
    p.append('<g transform="rotate(3 800 330)">')
    p.append('<rect x="756" y="282" width="84" height="94" fill="#000" opacity="0.16" transform="translate(3 4)"/>')
    p.append('<rect x="756" y="282" width="84" height="94" fill="#fffdf7" stroke="#9c9484" stroke-width="1.5"/>')
    for k, line in enumerate(("The Art of", "Computer", "Programming")):
        p.append(f'<text x="798" y="{298 + k * 8.5}" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="7.4" fill="{INK}">{line}</text>')
    p.append('<text x="798" y="330" text-anchor="middle" font-family="DejaVu Serif, serif" font-style="italic" font-size="5.6" fill="#555">D. E. Knuth, 1968-</text>')
    p.append(paper_lines(764, 336, 68, 4, gap=8, seed=9))
    p.append(reject_stamp(798, 350, 56, h=18, font=11, stroke=2.3, ls=0.5, rx=3, base=4.5))
    p.append(f'<circle cx="798" cy="286" r="4.5" fill="{RED}" stroke="#7a1015" stroke-width="1"/>')
    p.append('</g>')
    p.append('<g transform="rotate(-7 856 352)">')
    p.append('<rect x="828" y="336" width="62" height="30" fill="#000" opacity="0.15" transform="translate(2 3)"/>')
    p.append('<rect x="828" y="336" width="62" height="30" fill="#ffe680" stroke="#c9b24a" stroke-width="1"/>')
    p.append(f'<text x="859" y="355" text-anchor="middle" HAND font-weight="700" font-size="9.5" fill="{INK}">incomplete</text>')
    p.append('</g>')

    # ---- construction-site safety sign: days since last accept (404: accept not found) ----
    p.append('<defs><pattern id="hazard" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<rect width="14" height="14" fill="#f5c400"/><rect width="7" height="14" fill="#1a1a1a"/></pattern></defs>')
    p.append('<g transform="rotate(-2 100 246)">')
    p.append('<rect x="22" y="206" width="156" height="78" rx="4" fill="#000" opacity="0.18" transform="translate(3 4)"/>')
    p.append('<rect x="22" y="206" width="156" height="78" rx="4" fill="url(#hazard)" stroke="#1a1a1a" stroke-width="1.5"/>')
    p.append('<rect x="30" y="214" width="140" height="62" rx="2" fill="#fffdf7" stroke="#1a1a1a" stroke-width="1"/>')
    p.append(f'<text x="100" y="228" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="900" font-size="9" fill="{INK}" letter-spacing="0.8">DAYS SINCE</text>')
    p.append(f'<text x="100" y="239" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="900" font-size="9" fill="{INK}" letter-spacing="0.8">LAST ACCEPT</text>')
    for k, d in enumerate("404"):
        x = 73 + k * 19
        p.append(f'<rect x="{x}" y="244" width="16" height="26" rx="2" fill="#1f2228" stroke="#000" stroke-width="1"/>')
        p.append(f'<path d="M{x} 257 L{x + 16} 257" stroke="#000" stroke-width="1.2"/>')
        p.append(f'<text x="{x + 8}" y="265" text-anchor="middle" font-family="DejaVu Sans Mono, monospace" font-weight="700" font-size="19" fill="#fff">{d}</text>')
    p.append(f'<circle cx="100" cy="210" r="4" fill="{RED}" stroke="#7a1015" stroke-width="1"/>')
    p.append('</g>')

    # ---- framed world-record certificate on the wall, behind the mug ----
    p.append('<g transform="rotate(2 100 375)">')
    p.append('<rect x="26" y="292" width="150" height="168" fill="#000" opacity="0.18" transform="translate(4 5)"/>')
    p.append('<rect x="26" y="292" width="150" height="168" rx="2" fill="url(#gold)" stroke="#5c3f08" stroke-width="2"/>')
    p.append('<rect x="36" y="302" width="130" height="148" fill="#fbf4dc" stroke="#5c3f08" stroke-width="1.2"/>')
    p.append('<rect x="41" y="307" width="120" height="138" fill="none" stroke="#b08a3a" stroke-width="1" stroke-dasharray="3 2"/>')
    p.append('<text x="101" y="324" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="9" fill="#5c3f08" letter-spacing="1">OFFICIAL</text>')
    p.append('<text x="101" y="337" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="11" fill="#5c3f08" letter-spacing="0.5">WORLD RECORD</text>')
    p.append('<path d="M56 343 L146 343" stroke="#b08a3a" stroke-width="1"/>')
    p.append('<text x="101" y="356" text-anchor="middle" font-family="DejaVu Serif, serif" font-style="italic" font-size="7.5" fill="#3b2a05">Fastest peer review ever</text>')
    p.append(f'<text x="101" y="378" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="16" fill="{RED}">42 seconds</text>')
    p.append('<text x="101" y="389" text-anchor="middle" font-family="DejaVu Serif, serif" font-style="italic" font-size="5.6" fill="#3b2a05">including the time to find</text>')
    p.append('<text x="101" y="396" text-anchor="middle" font-family="DejaVu Serif, serif" font-style="italic" font-size="5.6" fill="#3b2a05">the reject button</text>')
    p.append('<text x="101" y="407" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="6.5" fill="#3b2a05">awarded to Reviewer 2</text>')
    p.append('<path d="M60 438 Q70 432 80 438 M122 438 Q132 432 142 438" stroke="#3b2a05" stroke-width="1" fill="none"/>')
    # seal with ribbons
    p.append(f'<path d="M95 424 L90 448 L97 443 L100 449 L102 424 Z" fill="{RED}"/><path d="M106 424 L104 449 L109 443 L114 448 L110 424 Z" fill="{RED_D}"/>')
    p.append('<circle cx="101" cy="423" r="10" fill="url(#gold)" stroke="#5c3f08" stroke-width="1.5"/>')
    p.append('<text x="101" y="427" text-anchor="middle" font-family="DejaVu Serif, serif" font-weight="700" font-size="11" fill="#5c3f08">2</text>')
    p.append('</g>')

    # ---- coffee mug ----
    p.append('<g>')
    p.append('<ellipse cx="102" cy="560" rx="62" ry="12" fill="url(#shadow)"/>')
    # handle: a flattened D with a real hole, attached under the body's edge, shaded like the body
    p.append('<path d="M 62 484 C 22 474 4 496 10 516 C 15 538 38 548 64 542 L 62 530 C 42 534 27 528 24 514 C 21 500 34 492 61 496 Z" fill="#000" opacity="0.12" transform="translate(4 6)"/>')
    p.append('<path d="M 62 484 C 22 474 4 496 10 516 C 15 538 38 548 64 542 L 62 530 C 42 534 27 528 24 514 C 21 500 34 492 61 496 Z" fill="url(#mughandle)" stroke="#8d8576" stroke-width="2" stroke-linejoin="round"/>')
    p.append('<path d="M 52 482 C 24 478 12 492 13 506" stroke="#fff" stroke-width="2.5" fill="none" opacity="0.8" stroke-linecap="round"/>')
    p.append('<path d="M 61 496 C 34 492 21 500 24 514 C 27 528 42 534 62 530" stroke="#000" stroke-width="2" fill="none" opacity="0.18"/>')
    p.append('<path d="M50 470 L56 552 Q95 566 134 552 L140 470 Z" fill="url(#mugbody)" stroke="#8d8576" stroke-width="2"/>')
    p.append('<path d="M57 548 Q95 561 133 548" stroke="#8d8576" stroke-width="3" fill="none" opacity="0.45" stroke-linecap="round"/>')
    p.append('<g clip-path="url(#mugclip)">')
    for txt, cy, size, bold in (("WORLD'S", 497, 11, True), ("#2", 521, 22, True), ("REVIEWER", 536, 11, True),
                                ("EST. 1665", 546, 6.5, False)):
        p.append(mug_text(txt, 95, cy, size, bold))
    p.append('</g>')
    p.append('<ellipse cx="95" cy="470" rx="45" ry="11" fill="url(#mugin)" stroke="#8d8576" stroke-width="2"/>')
    p.append('<ellipse cx="95" cy="474" rx="40" ry="8" fill="#2a170c"/>')
    p.append('<path d="M62 470 Q95 464 128 470" stroke="#6b4a33" stroke-width="1.5" fill="none" opacity="0.8"/>')
    p.append('</g>')

    # ---- reviewer guidelines pinned on the wall, used as a coaster ----
    p.append('<g transform="rotate(-4 100 110)">')
    p.append('<rect x="34" y="44" width="132" height="150" fill="#000" opacity="0.15" transform="translate(4 5)"/>')
    p.append('<rect x="34" y="44" width="132" height="150" fill="#fffdf7" stroke="#9c9484" stroke-width="1.5"/>')
    p.append(f'<text x="100" y="72" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="10" fill="{INK}">REVIEWER</text>')
    p.append(f'<text x="100" y="85" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="10" fill="{INK}">GUIDELINES</text>')
    p.append(f'<text x="100" y="106" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="14" fill="{RED}">4-page limit</text>')
    p.append(f'<text x="100" y="118" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="8.5" fill="{RED}">bibliography included</text>')
    p.append(f'<text x="100" y="129" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="8.5" fill="{RED}">no appendix allowed</text>')
    p.append(paper_lines(48, 138, 104, 5, 10, 3))
    p.append('<circle cx="112" cy="150" r="30" fill="none" stroke="#7a4a26" stroke-width="5" opacity="0.45"/>')
    p.append('<circle cx="112" cy="150" r="27" fill="none" stroke="#7a4a26" stroke-width="1.5" opacity="0.3"/>')
    p.append('<circle cx="100" cy="50" r="6" fill="#c1121f" stroke="#6b0a10" stroke-width="1.5"/>')
    p.append('</g>')

    # ---- review form, front right ----
    p.append('<g transform="matrix(1 0 0 0.88 0 66.4)">')
    p.append('<g transform="translate(16 -46) rotate(4 690 585)">')
    p.append('<rect x="604" y="540" width="196" height="118" rx="3" fill="#000" opacity="0.18" transform="translate(4 4)"/>')
    p.append('<rect x="604" y="540" width="196" height="118" rx="3" fill="#fdfcf8" stroke="#8d8576" stroke-width="1.5"/>')
    p.append(f'<text x="616" y="557" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="11" fill="{INK}">REVIEW FORM</text>')
    p.append(f'<text x="616" y="573" font-family="DejaVu Sans, sans-serif" font-size="9.5" fill="{INK}">Summary: <tspan font-style="italic">The authors propose...</tspan></text>')
    p.append(f'<text x="616" y="588" font-family="DejaVu Sans, sans-serif" font-size="9.5" fill="{INK}">Score: <tspan fill="{RED}" font-weight="700">-3 (strong reject)</tspan></text>')
    p.append(f'<text x="616" y="603" font-family="DejaVu Sans, sans-serif" font-size="9.5" fill="{INK}">Confidence: <tspan fill="{RED}" font-weight="700">5 (expert)</tspan></text>')
    for k, label in enumerate(('I read the abstract', 'I would have done it differently')):
        y = 610 + k * 14
        p.append(f'<rect x="616" y="{y}" width="9" height="9" fill="none" stroke="{INK}" stroke-width="1.2"/>')
        p.append(f'<path d="M617 {y + 4} L620 {y + 8} L627 {y - 3}" stroke="{RED}" stroke-width="2" fill="none"/>')
        p.append(f'<text x="631" y="{y + 8}" font-family="DejaVu Sans, sans-serif" font-size="9.5" fill="{INK}">{label}</text>')
    p.append(f'<text x="616" y="651" font-family="DejaVu Sans, sans-serif" font-size="9.5" fill="{INK}">Weakness: <tspan fill="{RED}" font-weight="700">not my method</tspan></text>')
    p.append('</g>')
    p.append('</g>')

    # ---- the submission under review: two A4 pages in perspective, printed side facing the reviewer ----
    p.append('<g transform="translate(180 448) skewX(-16) scale(1 0.42)">')
    for px in (0, 216):
        p.append(f'<rect x="{px + 7}" y="9" width="200" height="300" fill="#000" opacity="0.13"/>')
        p.append(f'<rect x="{px}" y="300" width="200" height="4" fill="#c9c2b2"/>')
        p.append(f'<rect x="{px}" y="0" width="200" height="300" fill="#fffdf7" stroke="#9c9484" stroke-width="1.6"/>')
        p.append(f'<path d="M{px} 0 L{px + 200} 0 M{px} 300 L{px + 200} 300" stroke="#9c9484" stroke-width="3.4"/>')
    # page 1, printed upside down for us: title, authors, two columns, and a hole where the related work should be
    p.append('<g transform="rotate(180 100 150)">')
    p.append(f'<rect x="22" y="22" width="156" height="11" rx="4" fill="{INK}" opacity="0.8"/>')
    p.append('<rect x="56" y="42" width="88" height="6" rx="3" fill="#8a8578"/>')
    p.append(paper_lines(14, 70, 82, 16, 13, 1))
    p.append(paper_lines(104, 70, 82, 16, 13, 3))
    p.append('<rect x="12" y="200" width="88" height="38" fill="#fffdf7"/>')
    p.append('</g>')
    # page 2, upside down too: text and the main figure, with its bars hanging from the top
    p.append('<g transform="rotate(180 316 150)">')
    p.append(paper_lines(230, 124, 82, 12, 13, 6))
    p.append(paper_lines(320, 124, 82, 12, 13, 7))
    p.append('</g>')
    # the reviewer's marks, written on the pages: readable for us
    p.append(f'<ellipse cx="144" cy="81" rx="54" ry="27" fill="none" stroke="{RED}" stroke-width="5" opacity="0.9"/>')
    p.append(f'<text x="14" y="293" HAND font-size="16" fill="{RED}">Cite R2 et al. [1-12]!</text>')
    # the same REJECT stamp as on the wall papers (scaled to this page), plus a faint second hit (he stamped it twice)
    p.append('<g opacity="0.2">' + reject_stamp(104, 210, 140, angle=-9) + '</g>')
    p.append(reject_stamp(96, 203, 140))
    # page 2: the main figure (upright), a coffee ring on it, and the verdict
    p.append('<rect x="232" y="194" width="168" height="84" fill="#fffdf7" stroke="#9c9484" stroke-width="1.5"/>')
    for i, h in enumerate((22, 34, 30, 48, 64)):
        p.append(f'<rect x="{246 + i * 30}" y="{272 - h}" width="18" height="{h}" fill="{"#2a7fc6" if i < 4 else "#d2232a"}" opacity="0.85"/>')
    p.append('<path d="M238 272 L396 272 M238 272 L238 200" stroke="#555" stroke-width="2"/>')
    p.append('<circle cx="350" cy="236" r="44" fill="#7a4a26" opacity="0.18"/>')
    p.append('<circle cx="350" cy="236" r="44" fill="none" stroke="#6b3c1c" stroke-width="6" opacity="0.5"/>')
    p.append('<circle cx="350" cy="236" r="39" fill="none" stroke="#6b3c1c" stroke-width="2" opacity="0.35"/>')
    p.append(f'<text x="226" y="176" font-family="DejaVu Sans, sans-serif" font-style="italic" font-size="23" fill="{RED}">unclear figure</text>')
    p.append('</g>')
    p.append(f'<text x="318" y="508" HAND font-size="20" fill="{RED}" transform="rotate(-8 318 508)">??</text>')

    # a small red pen lying on the paper, next to the circled hole it drew
    p.append('<g transform="rotate(-12 252 470)">')
    p.append('<rect x="212" y="466" width="86" height="9" rx="3" fill="#000" opacity="0.14" transform="translate(2 3)"/>')
    p.append('<rect x="214" y="465" width="80" height="9" rx="3" fill="url(#pen)" stroke="#5a0a0d" stroke-width="1.4"/>')
    p.append('<rect x="286" y="464" width="12" height="11" rx="2.5" fill="url(#metal)" stroke="#444" stroke-width="1"/>')
    p.append('<rect x="228" y="463.5" width="34" height="3" rx="1.5" fill="url(#metal)" stroke="#444" stroke-width="0.6"/>')
    p.append('<path d="M214 465 L201 469.5 L214 474 Z" fill="url(#metal)" stroke="#444" stroke-width="1"/>')
    p.append(f'<path d="M203 468.7 L196 469.5 L203 470.3 Z" fill="{RED}"/>')
    p.append('<rect x="232" y="467" width="50" height="2" rx="1" fill="#fff" opacity="0.4"/>')
    p.append('</g>')

    # ---- smartphone with a generic LLM chat ----
    p.append('<g transform="matrix(1 0 0 0.88 0 73.3)">')
    p.append('<g transform="rotate(-6 225 606)">')
    p.append('<rect x="152" y="578" width="146" height="66" rx="10" fill="#000" opacity="0.25" transform="translate(4 5)"/>')
    p.append('<rect x="152" y="578" width="146" height="66" rx="10" fill="#1c1d22" stroke="#0b0c0f" stroke-width="2"/>')
    p.append('<rect x="160" y="584" width="130" height="54" rx="5" fill="#f4f6fa"/>')
    p.append('<path d="M156 580.5 L294 580.5" stroke="#3a3c44" stroke-width="1"/>')
    p.append('<rect x="210" y="588" width="76" height="20" rx="6" fill="#3b82f6"/>')
    p.append('<text x="248" y="596" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="5.6" fill="#fff">Harsher. Sound expert.</text>')
    p.append('<text x="248" y="604" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="5.6" fill="#fff">Max 200 words.</text>')
    p.append('<rect x="164" y="611" width="96" height="24" rx="6" fill="#e2e5ec"/>')
    p.append(f'<text x="168" y="621" font-family="DejaVu Sans, sans-serif" font-size="5.6" font-weight="700" fill="{INK}">Certainly! Here is a review</text>')
    p.append(f'<text x="168" y="629" font-family="DejaVu Sans, sans-serif" font-size="5.6" fill="{INK}">harsher than the previous one:</text>')
    p.append('<path d="M160 584 L200 584 L170 638 L160 638 Z" fill="#fff" opacity="0.10"/>')
    p.append('</g>')
    p.append('</g>')

    # ---- a pad of pre-printed sticky notes ----
    p.append('<g transform="matrix(1 0 0 0.88 0 72.8)">')
    p.append('<g transform="rotate(5 395 607)">')
    p.append('<rect x="336" y="580" width="118" height="54" rx="2" fill="#000" opacity="0.2" transform="translate(3 4)"/>')
    for k in range(6, 0, -1):
        p.append(f'<rect x="{336 + k * 0.6:.1f}" y="{580 + k * 1.6:.1f}" width="118" height="54" rx="2" fill="{"#f2d75c" if k % 2 else "#e8c94a"}" stroke="#b39a2e" stroke-width="0.8"/>')
    p.append('<rect x="336" y="580" width="118" height="54" rx="2" fill="#ffe680" stroke="#b39a2e" stroke-width="1"/>')
    p.append(f'<text x="395" y="600" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-style="italic" font-weight="700" font-size="12" fill="{RED}">Ask for more</text>')
    p.append(f'<text x="395" y="616" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-style="italic" font-weight="700" font-size="12" fill="{RED}">experiments</text>')
    p.append('<text x="446" y="629" text-anchor="end" font-family="DejaVu Sans, sans-serif" font-size="6" fill="#7a6a20">pad of 500</text>')
    p.append('</g>')
    p.append('</g>')

    # ---- soft shadow of the mosquito ----
    p.append('<ellipse cx="495" cy="530" rx="210" ry="30" fill="url(#shadow)"/>')
    p.append('<ellipse cx="480" cy="528" rx="90" ry="12" fill="url(#shadow)"/>')

    # ---- mosquito ----
    # far wing
    p.append('<path d="M505 256 C560 180 690 150 760 165 C790 172 780 200 740 218 C660 252 580 270 507 268 Z" '
             'fill="url(#wing)" stroke="#6f7d8c" stroke-opacity="0.5" stroke-width="1.2" opacity="0.6"/>')
    # far legs, and both hind legs: behind the abdomen, darker
    far = dict(w0=7.5, fill="#3b3f4a", stroke="#262931", sheen=0.3)
    p.append(leg([(420, 368), (356, 392), (302, 432), (262, 506)], **far))
    p.append(leg([(440, 372), (402, 404), (376, 444), (354, 500)], **far))
    p.append(leg([(460, 368), (534, 381), (598, 414), (626, 496)], **far))
    p.append(leg([(470, 366), (568, 392), (634, 348), (724, 292)], w0=8.5, shadow=False))

    # abdomen with white bands and rim light
    p.append('<g transform="translate(600 300) rotate(-22)">')
    p.append('<path d="M-118 0 C-118 -30 -70 -40 -10 -38 C50 -36 100 -24 120 -8 C126 -3 126 5 118 10 C96 26 50 34 -10 36 C-70 38 -118 30 -118 0 Z" fill="url(#abd)" stroke="#0b0c0f" stroke-width="3"/>')
    p.append('<g clip-path="url(#abdclip)">')
    for x, bw in ((-80, 7), (-40, 7), (0, 6.5), (40, 5.5), (80, 4.5)):
        p.append(f'<path d="M{x} -40 Q{x + 12} 0 {x} 40" stroke="{WHITE}" stroke-width="{bw}" fill="none" opacity="0.9"/>')
        p.append(f'<path d="M{x + 9} -40 Q{x + 21} 0 {x + 9} 40" stroke="#000" stroke-width="2" fill="none" opacity="0.35"/>')
    p.append('<path d="M-118 0 C-118 -30 -70 -40 -10 -38 C50 -36 100 -24 120 -8 C126 -3 126 5 118 10 C96 26 50 34 -10 36 C-70 38 -118 30 -118 0 Z" fill="url(#abdshade)"/>')
    p.append('<path d="M-95 -22 Q0 -34 95 -16" stroke="#fff" stroke-opacity="0.25" stroke-width="6" fill="none" stroke-linecap="round"/>')
    p.append('<path d="M-60 30 Q20 38 95 18" stroke="#7f8aa0" stroke-opacity="0.45" stroke-width="2.5" fill="none" stroke-linecap="round"/>')
    p.append('</g>')
    p.append('</g>')

    # thorax with the silver dorsal stripe of the tiger mosquito
    p.append('<path d="M370 300 C370 240 430 215 485 235 C530 252 540 310 515 345 C490 380 410 385 385 355 C375 342 370 322 370 300 Z" '
             'fill="url(#thorax)" stroke="#0b0c0f" stroke-width="3"/>')
    p.append('<clipPath id="thoraxclip"><path d="M370 300 C370 240 430 215 485 235 C530 252 540 310 515 345 C490 380 410 385 385 355 C375 342 370 322 370 300 Z"/></clipPath>')
    # cast shadow of the head on the thorax
    p.append('<g clip-path="url(#thoraxclip)">')
    p.append('<ellipse cx="410" cy="300" rx="45" ry="55" fill="url(#shadow)" opacity="1"/>')
    for i in range(18):
        a = math.radians(200 + i * 9)
        if 225 <= 200 + i * 9 <= 320:
            continue
        x, y = 445 + 72 * math.cos(a), 300 + 62 * math.sin(a)
        p.append(f'<path d="M{x:.1f} {y:.1f} l{3 * math.cos(a):.1f} {3 * math.sin(a):.1f}" stroke="#6c7180" stroke-width="1.2"/>')
    p.append('<path d="M396 254 C428 226 476 226 508 254 C476 240 428 240 396 254 Z" fill="url(#silver)" stroke="#0b0c0f" stroke-width="1.5"/>')
    p.append('<path d="M470 370 Q510 352 522 318" stroke="#7f8aa0" stroke-opacity="0.45" stroke-width="2.5" fill="none" stroke-linecap="round"/>')
    p.append('</g>')

    # near wing with veins
    p.append('<path d="M510 250 C570 140 720 85 800 95 C835 100 828 130 790 152 C700 202 600 240 512 262 Z" '
             'fill="url(#wing)" stroke="#6f7d8c" stroke-opacity="0.6" stroke-width="1.2"/>')
    for d in ("M512 250 C570 150 700 98 800 97", "M514 253 C590 175 700 120 812 112",
              "M515 256 C600 195 700 145 806 128", "M516 259 C610 215 700 170 790 150",
              "M517 261 C620 232 690 205 740 180", "M518 262 C600 248 650 232 690 210"):
        p.append(f'<path d="{d}" stroke="#4f5d6d" stroke-opacity="0.4" stroke-width="1.1" fill="none"/>')
    p.append('<path d="M514 265 C600 243 700 205 792 155 C832 132 838 101 801 92" stroke="#6f7d8c" stroke-opacity="0.35" stroke-width="3" stroke-dasharray="1.5 2.5" fill="none"/>')

    p.append('<ellipse cx="511" cy="256" rx="7" ry="9" fill="#2a2d35" stroke="#0b0c0f" stroke-width="2"/>')
    # lanyard (both strands) and a landscape conference badge with a clip
    p.append('<path d="M360 300 C372 345 392 382 408 402" stroke="#16588f" stroke-width="9" fill="none" stroke-linecap="round"/>')
    p.append('<path d="M360 300 C372 345 392 382 408 402" stroke="#2a7fc6" stroke-width="6" fill="none" stroke-linecap="round"/>')
    p.append('<path d="M402 252 C424 300 428 362 414 402" stroke="#16588f" stroke-width="9" fill="none" stroke-linecap="round"/>')
    p.append('<path d="M402 252 C424 300 428 362 414 402" stroke="#2a7fc6" stroke-width="6" fill="none" stroke-linecap="round"/>')
    p.append('<g transform="translate(-6 28) rotate(-5 420 420)">')
    p.append('<rect x="413" y="372" width="16" height="14" rx="3" fill="url(#metal)" stroke="#555" stroke-width="1.2"/>')
    p.append('<rect x="362" y="384" width="144" height="96" rx="7" fill="#000" opacity="0.07" transform="translate(9 13)"/>')
    p.append('<rect x="361" y="383" width="146" height="98" rx="8" fill="#000" opacity="0.07" transform="translate(11 15)"/>')
    p.append('<rect x="362" y="384" width="144" height="96" rx="7" fill="#fffef9" stroke="#3a3d44" stroke-width="2"/>')
    p.append('<path d="M366 476 L366 392 Q366 388 370 388" stroke="#fff" stroke-width="1" fill="none" opacity="0.9"/>')
    p.append('<path d="M362 391 Q362 384 369 384 L499 384 Q506 384 506 391 L506 402 L362 402 Z" fill="#1f6fb2"/>')
    p.append('<text x="434" y="397" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="9" fill="#fff" letter-spacing="1">PC MEMBER</text>')
    p.append(f'<text x="392" y="452" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="58" fill="{INK}">2</text>')
    p.append(f'<text x="424" y="424" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="9" fill="#444">REVIEWER</text>')
    p.append('<text x="424" y="438" font-family="DejaVu Sans, sans-serif" font-size="8" fill="#555">Area: everything</text>')
    p.append('<text x="424" y="449" font-family="DejaVu Sans, sans-serif" font-size="7.5" fill="#555">Expertise: abstract</text>')
    p.append('<text x="424" y="460" font-family="DejaVu Sans, sans-serif" font-size="8" fill="#555">Time: 10 min</text>')
    p.append('<text x="371" y="474" font-family="DejaVu Sans, sans-serif" font-size="7.5" fill="#555">Conflicts: none (declared)</text>')
    p.append('</g>')

    # near legs: mid and hind planted, knees bent upward
    p.append('<g clip-path="url(#thoraxclip)"><ellipse cx="460" cy="372" rx="22" ry="8" fill="#000" opacity="0.35"/></g>')
    for cx, cy in ((450, 372), (470, 366)):
        p.append(f'<ellipse cx="{cx}" cy="{cy}" rx="9" ry="12" fill="url(#thorax)" stroke="#0b0c0f" stroke-width="1.6" transform="rotate(-30 {cx} {cy})"/>')
    p.append(leg([(450, 372), (516, 398), (572, 442), (568, 538)], w0=8.5))

    # front leg raising the REJECT stamp (behind the head), ghost outlines and speed lines toward the paper
    def stamp(dx=0, dy=0, ghost=0.0):
        q = [f'<g transform="translate({dx} {dy}) rotate(-14 245 140)"' + (f' opacity="{ghost}"' if ghost else '') + '>']
        if ghost:
            st = f'fill="none" stroke="{INK}" stroke-width="2"'
            q.append(f'<ellipse cx="245" cy="104" rx="18" ry="14" {st}/><rect x="236" y="110" width="18" height="40" rx="5" {st}/>')
            q.append(f'<rect x="204" y="148" width="82" height="16" rx="3" {st}/><rect x="200" y="162" width="90" height="18" rx="3" {st}/>')
        else:
            # varnished wooden knob with a highlight
            q.append('<ellipse cx="245" cy="102" rx="20" ry="15" fill="#7a4b2c" stroke="#3a2315" stroke-width="2.5"/>')
            q.append('<ellipse cx="238" cy="96" rx="8" ry="4.5" fill="#fff" opacity="0.35"/>')
            # turned neck with two rings
            q.append('<path d="M236 114 Q233 132 238 150 L252 150 Q257 132 254 114 Z" fill="#8f5a35" stroke="#3a2315" stroke-width="2.5" stroke-linejoin="round"/>')
            q.append('<path d="M235 122 L255 122 M235 140 L255 140" stroke="#3a2315" stroke-width="1.6" opacity="0.7"/>')
            q.append('<rect x="239" y="116" width="3" height="32" rx="1.5" fill="#fff" opacity="0.25"/>')
            # brass collar
            q.append('<rect x="226" y="148" width="38" height="7" rx="2" fill="#c9a24a" stroke="#6b5216" stroke-width="1.8"/>')
            # wooden block with grain, and the label on its side
            q.append('<rect x="200" y="154" width="90" height="22" rx="3" fill="#5b3a24" stroke="#2a1b12" stroke-width="2.5"/>')
            q.append('<rect x="202" y="155.5" width="86" height="4" rx="1.5" fill="#7a5236"/>')
            q.append('<rect x="202" y="171" width="86" height="3" fill="#3a2315" opacity="0.5"/>')
            q.append('<path d="M206 160 Q230 157 252 161 T284 159 M206 169 Q236 166 260 170 T284 168" stroke="#3a2315" stroke-width="1" fill="none" opacity="0.6"/>')
            q.append('<rect x="221" y="158" width="48" height="14" rx="2" fill="#f4ead2" stroke="#2a1b12" stroke-width="1"/>')
            q.append(f'<text x="245" y="168.5" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="8.5" fill="{RED}" letter-spacing="0.5">REJECT</text>')
            # inked red rubber, with a drip
            q.append(f'<rect x="203" y="176" width="84" height="9" rx="2" fill="url(#rubber)" stroke="{RED_D}" stroke-width="2"/>')
            q.append(f'<path d="M272 185 Q274 193 271 198 Q268 193 270 185 Z" fill="{RED}"/>')
        q.append('</g>')
        return "".join(q)
    p.append('<ellipse cx="232" cy="486" rx="46" ry="8" fill="#000" opacity="0.16"/>')
    p.append('<ellipse cx="232" cy="486" rx="24" ry="4" fill="#000" opacity="0.12"/>')
    p.append('<g transform="rotate(10 185 400) translate(-62 246)">' + stamp() + '</g>')
    # the front leg, over the stamp, and its claws wrapping the handle

    # stamp leg: femur from the front of the thorax, passing behind the head
    # head with rim light
    p.append(plumose(332, 204, 322, 140, 305, 92, hair=11))
    p.append(plumose(356, 198, 374, 132, 402, 94, hair=11))
    p.append('<circle cx="345" cy="262" r="62" fill="url(#head)" stroke="#0b0c0f" stroke-width="3"/>')
    p.append('<path d="M300 222 A62 62 0 0 1 395 220" stroke="#fff" stroke-opacity="0.35" stroke-width="3" fill="none" stroke-linecap="round"/>')
    p.append('<path d="M402 280 A59 59 0 0 1 362 318" stroke="#7f8aa0" stroke-opacity="0.45" stroke-width="2.5" fill="none" stroke-linecap="round"/>')
    # compound eyes: left lid low (bored), right lid high under a raised brow (suspicious)
    for cx, cy, rx, ry, lid in ((316, 257, 28, 32, 0.50), (374, 250, 25, 29, 0.30)):
        p.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#eye)" stroke="#0b0c0f" stroke-width="2.5"/>')
        p.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#hex)"/>')
        p.append(f'<ellipse cx="{cx + 5}" cy="{cy + 10}" rx="{rx * 0.42:.1f}" ry="{ry * 0.42:.1f}" fill="#0a0303"/>')
        p.append(f'<circle cx="{cx + 1}" cy="{cy + 9}" r="4.5" fill="#fff" opacity="0.9"/>')
        ly = cy - ry + 2 * ry * lid
        hw = rx * math.sqrt(max(0.0, 1 - ((ly - cy) / ry) ** 2)) + 2
        p.append(f'<path d="M{cx - hw:.1f} {ly:.1f} A{rx + 2} {ry + 2} 0 0 1 {cx + hw:.1f} {ly:.1f} Z" fill="#454a56" stroke="#0b0c0f" stroke-width="2.5"/>')
        p.append(f'<path d="M{cx - hw + 3:.1f} {ly - 4:.1f} L{cx + hw - 3:.1f} {ly - 4:.1f}" stroke="#6b7180" stroke-width="1.5" opacity="0.6"/>')
    p.append(f'<path d="M350 222 Q375 193 401 214" stroke="{INK}" stroke-width="7" fill="none" stroke-linecap="round"/>')
    # smug mouth corner, beside the snout
    p.append(f'<path d="M344 300 Q364 312 382 294 Q387 289 384 283" stroke="{INK}" stroke-width="4.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    p.append('<path d="M385 281 Q390 285 389 292" stroke="#8d93a3" stroke-opacity="0.5" stroke-width="2" fill="none" stroke-linecap="round"/>')

    # stamp leg: from the front of the thorax, under the head, behind the pen, to the handle
    p.append(leg([(392, 338), (340, 384), (262, 398), (204, 378)], w0=10.5, shadow=False))
    p.append(leg([(204, 378), (188, 364), (172, 372)], w0=5.2, w1=2.4, rings=0, shadow=False))
    # the lanyard's left strand passes in front of the stamp leg (redrawn below the head only)
    p.append('<clipPath id="belowhead"><rect x="0" y="323" width="900" height="317"/></clipPath>')
    p.append('<g clip-path="url(#belowhead)">')
    p.append('<path d="M360 300 C372 345 392 382 408 402" stroke="#16588f" stroke-width="9" fill="none" stroke-linecap="round"/>')
    p.append('<path d="M360 300 C372 345 392 382 408 402" stroke="#2a7fc6" stroke-width="6" fill="none" stroke-linecap="round"/>')
    p.append('</g>')
    # proboscis: a thin, slightly curved needle from the snout down to the paper
    p.append('<path d="M303 321 Q285 360 271 384 L269.5 383 Q280 358 299 319 Z" fill="#000" opacity="0.15" transform="translate(4 3)"/>')
    p.append(f'<path d="M303.5 320 Q285.5 360 271 385 L269.5 384 Q280.5 358 299.5 318 Z" fill="#2a2d35" stroke="#0b0c0f" stroke-width="1.2" stroke-linejoin="round"/>')
    # snout: a tapered cone in line with the proboscis
    dx, dy, nx, ny = -0.5, 0.866, 0.866, 0.5
    s0x, s0y = 300 - dx * 30, 323 - dy * 30
    e0x, e0y = 300 - dx * 2, 323 - dy * 2
    pts = [(s0x + nx * 8, s0y + ny * 8), (e0x + nx * 4, e0y + ny * 4), (e0x - nx * 4, e0y - ny * 4), (s0x - nx * 8, s0y - ny * 8)]
    p.append('<path d="M' + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + ' Z" fill="#2a2d35" stroke="#0b0c0f" stroke-width="2.5" stroke-linejoin="round"/>')
    p.append(f'<path d="M{s0x + nx * 4:.1f} {s0y + ny * 4:.1f} L{e0x + nx * 2:.1f} {e0y + ny * 2:.1f}" stroke="#8d93a3" stroke-opacity="0.5" stroke-width="2" stroke-linecap="round"/>')

    p.append('<rect width="900" height="640" fill="url(#vignette)"/>')
    p.append('</svg>')
    out = "\n".join(p).replace("HAND", 'font-family="DejaVu Sans, sans-serif" font-style="italic"')
    return soften(out)


def soften(svg_text):
    """Hard drop shadows become 3 stacked soft ones; pins get a highlight and a shadow."""
    import re

    def shadow(m):
        x, y, w, h, rx = float(m[1]), float(m[2]), float(m[3]), float(m[4]), m[5] or ""
        out = []
        for k, (ox, oy) in enumerate(((2, 3), (4, 5), (6, 8))):
            g = k * 1.0
            out.append(f'<rect x="{x - g:.1f}" y="{y - g:.1f}" width="{w + 2 * g:.1f}" height="{h + 2 * g:.1f}"{rx} '
                       f'fill="#000" opacity="0.07" transform="translate({ox} {oy})"/>')
        return "".join(out)
    svg_text = re.sub(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"( rx="[\d.]+")? '
                      r'fill="#000" opacity="0\.(?:1[5-9]|2\d?)" transform="translate\([\d.]+ [\d.]+\)"/>', shadow, svg_text)

    def pin(m):
        cx, cy, r = float(m[1]), float(m[2]), float(m[3])
        return (f'<circle cx="{cx + 3:.1f}" cy="{cy + 3:.1f}" r="{r:.1f}" fill="#000" opacity="0.2"/>' + m[0] +
                f'<circle cx="{cx - 1.5:.1f}" cy="{cy - 1.5:.1f}" r="1.5" fill="#fff" opacity="0.8"/>')
    return re.sub(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" fill="(?:#d2232a|#c1121f)" '
                  r'stroke="#(?:7a1015|6b0a10)" stroke-width="[\d.]+"/>', pin, svg_text)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "reviewer2.svg"
    s = svg()
    open(out, "w").write(s)
    if len(sys.argv) > 2:
        import cairosvg
        cairosvg.svg2png(bytestring=s.encode(), write_to=sys.argv[2], output_width=1350)
