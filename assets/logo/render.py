"""Run a drawing script (or render an SVG) with the DejaVu fonts registered, on macOS.

cairosvg on macOS finds fonts through CoreText, which does not see DejaVu unless it is installed system-wide; without
it every text of the illustration silently falls back to Helvetica. This wrapper registers the DejaVu TrueType files
shipped with TeX Live for this process only (nothing is installed), then runs the script.

Usage, from the repository root:
  python3 assets/logo/render.py assets/logo/draw_reviewer2.py assets/logo/reviewer2.svg assets/logo/reviewer2.png
  python3 assets/logo/render.py assets/logo/draw_logo.py
  python3 assets/logo/render.py --svg in.svg out.png                     # render one SVG at 1350 px width
cairosvg need not be installed: `uv run --no-project --with cairosvg python assets/logo/render.py ...` runs it in
a temporary environment. On Linux, install the DejaVu fonts (fonts-dejavu) and run the drawing scripts directly.
"""
import ctypes
import glob
import runpy
import sys

FONTS = glob.glob("/usr/local/texlive/*/texmf-dist/fonts/truetype/public/dejavu/DejaVu*.ttf")

if sys.platform == "darwin" and FONTS:
    CF = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    CT = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreText.framework/CoreText")
    CF.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    CF.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
    CT.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    for f in FONTS:
        b = f.encode()
        u = CF.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False)
        CT.CTFontManagerRegisterFontsForURL(u, 1, None)  # 1 = process scope
elif sys.platform == "darwin":
    print("warning: DejaVu fonts not found under /usr/local/texlive: text will fall back to Helvetica", file=sys.stderr)

if len(sys.argv) >= 4 and sys.argv[1] == "--svg":
    import cairosvg
    cairosvg.svg2png(url=sys.argv[2], write_to=sys.argv[3], output_width=1350)
elif len(sys.argv) >= 2:
    sys.argv = sys.argv[1:]
    runpy.run_path(sys.argv[0], run_name="__main__")
else:
    print(__doc__)
