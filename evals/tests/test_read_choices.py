#!/usr/bin/env python3
"""Tests of read_choices.py: the author's "do it" check boxes and typed answers (answer-N text fields) read back from a
saved changes.pdf (plain PDF, a viewer's incremental save, compressed object streams with an xref stream, and a PDF
written by pdfTeX). Invented content only.

Run: python3 -I evals/tests/test_read_choices.py
"""
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "reviewer2-repellent" / "scripts" / "read_choices.py"
spec = importlib.util.spec_from_file_location("read_choices", SCRIPT)
RC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RC)

AP = b"/AP << /N << /Yes 9 0 R /Off 10 0 R >> >>"
# the field objects: item-12 with two widgets, item-3 merged field+widget, item-5 read-only (facts, ticked but read
# only), item-20 with a hex name and no /V (its widget decides), and a field that is not an item
FIELDS = {
    4: b"<< /FT /Btn /T (item-12) /V /Yes /Kids [5 0 R 6 0 R] >>",
    5: b"<< /Type /Annot /Subtype /Widget /Parent 4 0 R /AS /Yes /Rect [10 10 19 19] " + AP + b" >>",
    6: b"<< /Type /Annot /Subtype /Widget /Parent 4 0 R /AS /Yes /Rect [10 30 19 39] " + AP + b" >>",
    7: b"<< /Type /Annot /Subtype /Widget /FT /Btn /T (item-3) /V /Off /AS /Off /Rect [30 10 39 19] " + AP + b" >>",
    8: b"<< /Type /Annot /Subtype /Widget /FT /Btn /T (item-5) /Ff 1 /V /Yes /AS /Yes /Rect [50 10 59 19] >>",
    11: b"<< /FT /Btn /T <6974656D2D3230> /Kids [12 0 R] >>",
    12: b"<< /Type /Annot /Subtype /Widget /Parent 11 0 R /AS /On /Rect [70 10 79 19] >>",
    13: b"<< /FT /Tx /T (note \\(free\\) text) /V (hello) >>",
}
BASE = {
    1: b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R 7 0 R 8 0 R 11 0 R 13 0 R] >> >>",
    2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Annots [5 0 R 6 0 R 7 0 R 8 0 R 12 0 R] >>",
}


def stream_obj(dic, data):
    return dic.rstrip(b">").rstrip() + b" /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"


XOBJ = {9: stream_obj(b"<< /Type /XObject /Subtype /Form /BBox [0 0 9 9] >>", b"0 0 9 9 re S"),
        10: stream_obj(b"<< /Type /XObject /Subtype /Form /BBox [0 0 9 9] >>", b"0 0 9 9 re s")}


def body(objs, start):
    """Objects written from offset start: (bytes, {num: offset})."""
    out, offs = b"", {}
    for n in sorted(objs):
        offs[n] = start + len(out)
        out += b"%d 0 obj\n" % n + objs[n] + b"\nendobj\n"
    return out, offs


def xref_table(offs, size, prev=None, start=0):
    """A classic xref section for the given offsets (subsections of consecutive numbers) and its trailer."""
    nums = sorted(offs)
    out = b"xref\n"
    if 0 not in offs and prev is None:
        nums = [0] + nums
    groups, cur = [], []
    for n in nums:
        if cur and n != cur[-1] + 1:
            groups.append(cur)
            cur = []
        cur.append(n)
    if cur:
        groups.append(cur)
    for g in groups:
        out += b"%d %d\n" % (g[0], len(g))
        for n in g:
            out += (b"0000000000 65535 f \n" if n == 0 else b"%010d 00000 n \n" % offs[n])
    out += b"trailer\n<< /Size %d /Root 1 0 R%s >>\n" % (size, (b" /Prev %d" % prev) if prev is not None else b"")
    out += b"startxref\n%d\n%%%%EOF\n" % start
    return out


def plain_pdf():
    head = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    objs = {**BASE, **FIELDS, **XOBJ}
    b, offs = body(objs, len(head))
    x = len(head) + len(b)
    return head + b + xref_table(offs, 14, start=x), x


def incremental(pdf, prev):
    """A viewer save: item-12 unticked (/V and both widgets), item-3 ticked, appended as an update."""
    upd = {4: FIELDS[4].replace(b"/V /Yes", b"/V /Off"),
           5: FIELDS[5].replace(b"/AS /Yes", b"/AS /Off"),
           6: FIELDS[6].replace(b"/AS /Yes", b"/AS /Off"),
           7: FIELDS[7].replace(b"/V /Off /AS /Off", b"/V /Yes /AS /Yes")}
    b, offs = body(upd, len(pdf))
    x = len(pdf) + len(b)
    return pdf + b + xref_table(offs, 14, prev=prev, start=x)


def objstm(objs, num):
    """A Flate-compressed object stream holding objs: (object bytes, [(obj num, index)])."""
    hdr, data, idx = [], b"", []
    for k, n in enumerate(sorted(objs)):
        hdr.append(b"%d %d" % (n, len(data)))
        data += objs[n] + b"\n"
        idx.append((n, k))
    h = b" ".join(hdr) + b"\n"
    raw = zlib.compress(h + data)
    dic = b"<< /Type /ObjStm /N %d /First %d /Filter /FlateDecode >>" % (len(objs), len(h))
    return stream_obj(dic, raw), idx


def xref_stream(entries, num, size, start, prev=None):
    """An xref stream object: entries {obj: (type, f2, f3)}, /W [1 4 2]."""
    rows, index = b"", []
    for n in sorted(entries):
        t, a, b = entries[n]
        rows += bytes([t]) + a.to_bytes(4, "big") + b.to_bytes(2, "big")
        index += [n, 1]
    dic = b"<< /Type /XRef /Size %d /W [1 4 2] /Index [%s] /Root 1 0 R%s /Filter /FlateDecode >>" % (
        size, b" ".join(b"%d" % i for i in index), (b" /Prev %d" % prev) if prev is not None else b"")
    obj = b"%d 0 obj\n" % num + stream_obj(dic, zlib.compress(rows)) + b"\nendobj\n"
    return obj + b"startxref\n%d\n%%%%EOF\n" % start


def compressed_pdf(update=True):
    """Fields in an object stream (obj 20), xref stream (obj 21); then an update whose new object stream (obj 22)
    redefines item-12 as unticked, with its own xref stream (obj 23)."""
    head = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    top = {**BASE, **XOBJ}
    b, offs = body(top, len(head))
    stm, idx = objstm(FIELDS, 20)
    pos = len(head) + len(b)
    b += b"20 0 obj\n" + stm + b"\nendobj\n"
    entries = {0: (0, 0, 65535)}
    entries.update({n: (1, o, 0) for n, o in offs.items()})
    entries[20] = (1, pos, 0)
    entries.update({n: (2, 20, k) for n, k in idx})
    x = len(head) + len(b)
    entries[21] = (1, x, 0)
    pdf = head + b + xref_stream(entries, 21, 22, x)
    if not update:
        return pdf
    stm2, idx2 = objstm({4: FIELDS[4].replace(b"/V /Yes", b"/V /Off")}, 22)
    p2 = len(pdf)
    add = b"22 0 obj\n" + stm2 + b"\nendobj\n"
    x2 = p2 + len(add)
    e2 = {22: (1, p2, 0), 23: (1, x2, 0)}
    e2.update({n: (2, 22, k) for n, k in idx2})
    return pdf + add + xref_stream(e2, 23, 24, x2, prev=x)


DEFAULTS = (
    "\\rritemstate{12}{1}{0}{default: do -- certain fix}\n"
    "\\rritemstate{3}{0}{0}{default: don't -- optional wording}\n"
    "\\rritemstate{5}{0}{1}{default: don't -- needs your facts}\n"
    "\\rritemstate{20}{1}{0}{default: do -- fix to confirm, 50\\% sure}\n"
    "\\rritemstate{99}{1}{0}{default: do -- certain fix}\n")


class ReadChoices(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="choices-"))
        (self.tmp / "states.tex").write_text(DEFAULTS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, data, name="changes.pdf"):
        p = self.tmp / name
        p.write_bytes(data)
        return str(p)

    def test_plain(self):
        pdf, _ = plain_pdf()
        p = self.write(pdf)
        self.assertEqual(RC.read_fields(p), {12: (True, False), 3: (False, False), 5: (True, True),
                                             20: (True, False)})
        res = RC.choices(p, str(self.tmp / "states.tex"))
        self.assertEqual(res["do"], [12, 20])
        self.assertEqual(res["dont"], [3, 5])                 # item 5 is read-only: never applied
        self.assertEqual(res["changed"], [])
        self.assertEqual(res["missing"], [99])
        self.assertEqual(res["items"]["20"]["reason"], "default: do – fix to confirm, 50% sure")
        self.assertTrue(res["items"]["5"]["readonly"])

    def test_without_defaults(self):
        pdf, _ = plain_pdf()
        res = RC.choices(self.write(pdf))
        self.assertIsNone(res["items"]["12"]["default"])
        self.assertEqual(res["changed"], [])

    def test_incremental_save(self):
        pdf, x = plain_pdf()
        p = self.write(incremental(pdf, x))
        self.assertEqual(RC.read_fields(p)[12], (False, False))
        self.assertEqual(RC.read_fields(p)[3], (True, False))
        res = RC.choices(p, RC.load_defaults(str(self.tmp / "states.tex")))
        self.assertEqual(res["do"], [3, 20])
        self.assertEqual(res["changed"], [3, 12])
        self.assertFalse(res["items"]["20"]["changed"])

    def test_object_streams(self):
        p = self.write(compressed_pdf(update=False), "c0.pdf")
        self.assertEqual(RC.read_fields(p), {12: (True, False), 3: (False, False), 5: (True, True),
                                             20: (True, False)})
        p = self.write(compressed_pdf(), "c1.pdf")
        res = RC.choices(p, str(self.tmp / "states.tex"))
        self.assertEqual(res["do"], [20])
        self.assertEqual(res["changed"], [12])

    def test_cli(self):
        pdf, x = plain_pdf()
        p = self.write(incremental(pdf, x))
        (self.tmp / "work" / "marked").mkdir(parents=True)
        shutil.copy(self.tmp / "states.tex", self.tmp / "work" / "marked" / "r2states.tex")
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("4 items: 2 do, 2 don't, 2 changed from the default", r.stdout)
        res = json.loads((self.tmp / "work" / "choices.json").read_text())
        self.assertEqual(res["changed"], [3, 12])

    def test_no_fields(self):
        head = b"%PDF-1.7\n"
        b, offs = body(BASE, len(head))
        p = self.write(head + b + xref_table(offs, 4, start=len(head) + len(b)))
        with self.assertRaises(ValueError):
            RC.choices(p)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), p, "--out", str(self.tmp / "c.json")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no item-N check box fields", r.stderr)

    @unittest.skipUnless(shutil.which("pdflatex"), "pdflatex not installed")
    def test_answers(self):
        # answer-N text fields: empty as built; a viewer save fills them (UTF-16BE hex with BOM, a literal with
        # escapes and CR line breaks, PDFDocEncoding, UTF-8 with BOM), blanks and non-answer fields are left out
        ans = {30: b"<< /FT /Tx /T (answer-12) /Ff 4096 /V () /Rect [10 50 190 80] >>",
               31: b"<< /FT /Tx /T (answer-3) /Ff 4096 /V () /Rect [10 90 190 120] >>",
               32: b"<< /FT /Tx /T (answer-5) /Ff 4096 /V () /Rect [10 130 190 160] >>",
               33: b"<< /FT /Tx /T (answer-20) /Ff 4096 /V () /Rect [10 170 190 199] >>",
               34: b"<< /FT /Tx /T (answer-21) /Ff 4096 /V () /Rect [10 10 190 40] >>"}
        head = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
        base = dict(BASE)
        base[1] = base[1].replace(b"13 0 R]", b"13 0 R 30 0 R 31 0 R 32 0 R 33 0 R 34 0 R]")
        objs = {**base, **FIELDS, **XOBJ, **ans}
        b, offs = body(objs, len(head))
        x = len(head) + len(b)
        pdf = head + b + xref_table(offs, 35, start=x)
        self.assertEqual(RC.read_answers(self.write(pdf, "a0.pdf")), {})
        self.assertEqual(RC.choices(self.write(pdf, "a0.pdf"))["answers"], {})
        quokka = "It is 2.4\u00d7 \u2014 Ada Burrow\u2019s quokkas \u00fc\nsecond line"
        upd = {30: ans[30].replace(b"/V ()", b"/V <FEFF" + quokka.encode("utf-16-be").hex().upper().encode() + b">"),
               31: ans[31].replace(b"/V ()", b"/V (Wombats \\(all\\) dig\\r\\nat night\\rtoo \\\\ \\101)"),
               32: ans[32].replace(b"/V ()", b"/V (8 threads \\204 32 cores)"),
               33: ans[33].replace(b"/V ()", b"/V <EFBBBF" + "Numbat \u00e9".encode("utf-8").hex().encode() + b">"),
               34: ans[34].replace(b"/V ()", b"/V (  \\r )")}
        b2, offs2 = body(upd, len(pdf))
        x2 = len(pdf) + len(b2)
        p = self.write(pdf + b2 + xref_table(offs2, 35, prev=x, start=x2), "a1.pdf")
        self.assertEqual(RC.read_answers(p), {12: quokka, 3: "Wombats (all) dig\nat night\ntoo \\ A",
                                              5: "8 threads \u2014 32 cores", 20: "Numbat \u00e9"})
        res = RC.choices(p, str(self.tmp / "states.tex"))
        self.assertEqual(list(res["answers"]), ["3", "5", "12", "20"])
        self.assertEqual(res["answers"]["12"], quokka)
        self.assertEqual(res["do"], [12, 20])                  # the boxes are read as before
        self.assertNotIn("note (free) text", json.dumps(res))  # other text fields are not answers
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), p, "--out", str(self.tmp / "a.json")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("4 answers", r.stdout)
        self.assertEqual(json.loads((self.tmp / "a.json").read_text(encoding="utf-8"))["answers"]["12"], quokka)

    def test_pdftex(self):
        tex = r"""\pdfobjcompresslevel=2 \pdfminorversion=7
\documentclass{article}
\begin{document}
\pdfobj reserveobjnum \edef\fa{\the\pdflastobj}
\pdfobj reserveobjnum \edef\fb{\the\pdflastobj}
\pdfannot reserveobjnum \edef\wa{\the\pdflastannot}
\pdfannot reserveobjnum \edef\wb{\the\pdflastannot}
\pdfannot reserveobjnum \edef\wc{\the\pdflastannot}
Item 7 \pdfannot useobjnum \wa width 9bp height 9bp depth 0pt {/Subtype/Widget/Parent \fa\space 0 R/AS/Yes/F 4}
and again \pdfannot useobjnum \wb width 9bp height 9bp depth 0pt {/Subtype/Widget/Parent \fa\space 0 R/AS/Yes/F 4}
item 8 \pdfannot useobjnum \wc width 9bp height 9bp depth 0pt {/Subtype/Widget/Parent \fb\space 0 R/AS/Off/F 4}
\immediate\pdfobj useobjnum \fa {<</FT/Btn/T(item-7)/V/Yes/Kids[\wa\space 0 R \wb\space 0 R]>>}
\immediate\pdfobj useobjnum \fb {<</FT/Btn/T(item-8)/V/Off/Ff 1/Kids[\wc\space 0 R]>>}
\pdfcatalog{/AcroForm<</Fields[\fa\space 0 R \fb\space 0 R]>>}
\end{document}
"""
        (self.tmp / "t.tex").write_text(tex)
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "t.tex"], cwd=self.tmp,
                       capture_output=True)
        p = self.tmp / "t.pdf"
        self.assertTrue(p.is_file())
        self.assertEqual(RC.read_fields(str(p)), {7: (True, False), 8: (False, True)})


if __name__ == "__main__":
    unittest.main(verbosity=2)
