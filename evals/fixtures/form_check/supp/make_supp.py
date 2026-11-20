#!/usr/bin/env python3
"""Builds the --supp fixtures in DEST: dirty/ and clean/ folders and dirty.zip.

Files git cannot hold or ignores (.git/, .env, .DS_Store, PDFs) and binary ones (PDF, .docx, .zip) are generated
here; the readable ones (README.md, LICENSE, analysis.ipynb, src/train.py) are copied from dirty/ and clean/.
All people, institutions and keys are invented ("Ada Burrow", Northwind University, a fake sk- key).
Run: python3 -I make_supp.py DEST
"""
import pathlib
import shutil
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent


def pdf(author):
    """A one-page PDF with an Info dictionary, written by hand (offsets computed)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
            b"<< /Title (Extra results) /Author (" + author.encode() + b") /Creator (LaTeX with hyperref) >>"]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 4 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def docx(path, creator):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document><w:body/></w:document>')
        z.writestr("docProps/core.xml",
                   '<?xml version="1.0"?><cp:coreProperties><dc:creator>' + creator + '</dc:creator>'
                   '<cp:lastModifiedBy>' + creator + '</cp:lastModifiedBy></cp:coreProperties>')


def build(dest):
    dest = pathlib.Path(dest)
    for name in ("dirty", "clean"):
        if (dest / name).exists():
            shutil.rmtree(dest / name)
        shutil.copytree(HERE / name, dest / name)
    d = dest / "dirty"
    (d / ".git" / "logs").mkdir(parents=True)
    (d / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (d / ".git" / "config").write_text(
        "[core]\n\trepositoryformatversion = 0\n[user]\n\tname = Ada Burrow\n\temail = ada.burrow@northwind.edu\n"
        '[remote "origin"]\n\turl = https://github.com/aburrow/fastidx.git\n')
    (d / ".git" / "logs" / "HEAD").write_text(
        "0000000000000000000000000000000000000000 3f2a9c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39 Ada Burrow "
        "<ada.burrow@northwind.edu> 1735689600 +0100\tcommit (initial): first version\n")
    (d / ".env").write_text("OPENAI_API_KEY=sk-test-FAKEFAKEFAKEFAKEFAKE1234\nDEBUG=1\n")
    (d / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1" + b"\x00" * 32)
    (d / "report.pdf").write_bytes(pdf("Ada Burrow"))
    docx(d / "notes.docx", "Ada Burrow")
    (dest / "clean" / "report.pdf").write_bytes(pdf(""))
    docx(dest / "clean" / "notes.docx", "")
    # the same material as an archive made on macOS (with __MACOSX/), holding a nested code archive
    with zipfile.ZipFile(dest / "dirty.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                z.write(f, "dirty/" + f.relative_to(d).as_posix())
        z.writestr("__MACOSX/dirty/._README.md", b"\x00\x05\x16\x07")
        inner = dest / "code.zip"
        with zipfile.ZipFile(inner, "w") as zi:
            zi.writestr("eval/run.sh", "python eval.py --data /Users/aburrow/datasets/msmarco\n")
        z.write(inner, "dirty/code.zip")
        inner.unlink()


if __name__ == "__main__":
    build(sys.argv[1])
