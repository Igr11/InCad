"""Picture ▸ Insert Picture (the user: "JPG for reference"), and Scale Picture (the user: a
photo of something measured — this length is so much — and the rest scales with it)."""
import os
import shutil
import struct
import tempfile
import unittest
import zlib

import FreeCAD as App
from incad.core import document, image_reference, line3d
from incad.features import kind_for, picture_scale
from headless import util

V = App.Vector


def write_png(path, w, h):
    """A plain grey PNG of w x h pixels (no Qt needed)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class ImportMore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_import_more_")
        self.doc = util.new_doc("ImpM")
        document.make_part(self.doc)
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_picture_and_its_scale(self):
        path = os.path.join(self.dir, "photo.png")
        write_png(path, 400, 200)
        pic = image_reference.add(self.doc, path)
        self.assertTrue(image_reference.is_picture(pic))
        self.assertIs(kind_for(pic), picture_scale)
        self.assertEqual((round(pic.XSize.Value, 6), round(pic.YSize.Value, 6)), (100, 50))  # proportions kept
        k = picture_scale
        k.read(self.doc, pic)
        first = pic.Placement.multVec(k.local(pic, 0.25, 0.5))
        values = {"points": line3d.format_points([(0.25, 0.5, 0), (0.75, 0.5, 0)]), "length": "120 mm"}
        k.update(self.doc, pic, values)  # 50 mm on the picture is really 120 mm
        self.assertAlmostEqual(pic.XSize.Value, 240, places=6)
        self.assertAlmostEqual(pic.YSize.Value, 120, places=6)
        self.assertAlmostEqual((pic.Placement.multVec(k.local(pic, 0.25, 0.5)) - first).Length, 0, places=6)
        self.assertEqual(k.info(values), "On the image now: 120 mm")
        k.update(self.doc, pic, dict(values, length="60 mm"))  # from the size it opened with, not compounded
        self.assertAlmostEqual(pic.XSize.Value, 120, places=6)
        k.update(self.doc, pic, dict(values, points=""))
        self.assertAlmostEqual(pic.XSize.Value, 100, places=6)
        self.assertFalse(k.pending({"points": "", "length": ""}))  # the transparency alone can be kept
        self.assertTrue(k.pending({"points": "0.1 0.1 0", "length": ""}))
