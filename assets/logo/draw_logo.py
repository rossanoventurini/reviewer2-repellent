"""Draw the reviewer2-repellent logo: the label of the spray can, on its own.

python3 draw_logo.py            writes logo.svg and PNGs at 512, 256, 128 and 64 px wide
"""
import cairosvg

INK = "#16181d"
RED = "#d2232a"
EDGE = "#0b3a26"


def mosquito(cx, cy, s, color=INK):
    """A small mosquito silhouette centred at (cx, cy), scale s."""
    q = []
    q.append(f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{color}" stroke-linecap="round" stroke-linejoin="round">')
    q.append('<ellipse cx="18" cy="-4" rx="20" ry="6" transform="rotate(-18 18 -4)" fill="{c}" stroke="none"/>'.replace("{c}", color))
    q.append(f'<circle cx="-6" cy="2" r="9" fill="{color}" stroke="none"/>')
    q.append(f'<circle cx="-17" cy="3" r="6" fill="{color}" stroke="none"/>')
    q.append('<path d="M-22 6 L-40 16" stroke-width="2.5"/>')
    q.append('<path d="M-2 -6 C6 -30 26 -34 36 -30 C30 -20 14 -12 0 -4" stroke-width="2" fill="#ffffff" fill-opacity="0.6"/>')
    for d in ("M-8 9 L-18 22 L-24 34", "M-4 10 L-4 24 L-10 36", "M0 9 L12 22 L14 34"):
        q.append(f'<path d="{d}" stroke-width="2.2"/>')
    q.append('</g>')
    return "".join(q)


def svg():
    # the label of the spray can: x 146..316, y 200..416, with a small margin
    return "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="140 194 182 228" width="364" height="456">',
        '<title>reviewer2-repellent</title>',
        '<defs><clipPath id="label"><rect x="146" y="200" width="170" height="216" rx="6"/></clipPath></defs>',
        f'<rect x="146" y="200" width="170" height="216" rx="6" fill="#fdfbf4" stroke="{EDGE}" stroke-width="2.5"/>',
        '<g clip-path="url(#label)">',
        f'<rect x="146" y="200" width="170" height="34" fill="{RED}"/>',
        '<text x="231" y="223" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" '
        'font-size="17" fill="#fff" letter-spacing="2">REVIEWER 2</text>',
        f'<text x="231" y="256" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-weight="700" '
        f'font-size="22" fill="{INK}" letter-spacing="1">REPELLENT</text>',
        mosquito(234, 318, 1.25),
        f'<circle cx="231" cy="314" r="46" fill="none" stroke="{RED}" stroke-width="8"/>',
        f'<path d="M199 282 L263 346" stroke="{RED}" stroke-width="8" stroke-linecap="round"/>',
        f'<text x="231" y="384" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-style="italic" '
        f'font-size="12" fill="{INK}">Spray before you submit</text>',
        '<text x="231" y="404" text-anchor="middle" font-family="DejaVu Sans, sans-serif" font-size="8.5" '
        'fill="#555">Lasts one review cycle</text>',
        '</g>',
        f'<rect x="146" y="200" width="170" height="216" rx="6" fill="none" stroke="{EDGE}" stroke-width="2.5"/>',
        '</svg>',
    ])


if __name__ == "__main__":
    s = svg()
    open("logo.svg", "w").write(s)
    for px in (512, 256, 128, 64):
        cairosvg.svg2png(bytestring=s.encode(), write_to="logo.png" if px == 512 else f"logo_{px}.png",
                         output_width=px)
