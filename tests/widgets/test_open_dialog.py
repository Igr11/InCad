"""The Open window's picture (the user: a preview of the file before opening it, STL too): an STL is drawn shaded, a
binary one and an ASCII one; the window has no icon provider of its own (Qt asks for icons from a worker thread,
where a picture can't be made: InnCad hung on a folder)."""
import os
import struct
import tempfile
import unittest

from widgets import qtapp
from incad.ui import open_dialog

BG = (43, 47, 54)


def box_triangles(w=20.0, d=10.0, h=6.0):
    v = [(0, 0, 0), (w, 0, 0), (w, d, 0), (0, d, 0), (0, 0, h), (w, 0, h), (w, d, h), (0, d, h)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7),
             (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [[v[i] for i in f] for f in faces]


class StlPicture(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.dir = tempfile.mkdtemp()

    def write_binary(self, name):
        path = os.path.join(self.dir, name)
        tris = box_triangles()
        with open(path, "wb") as f:
            f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
            for t in tris:
                f.write(struct.pack("<3f", 0, 0, 0))
                for p in t:
                    f.write(struct.pack("<3f", *p))
                f.write(b"\0\0")
        return path

    def write_ascii(self, name):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write("solid box\n")
            for t in box_triangles():
                f.write("facet normal 0 0 0\nouter loop\n")
                for p in t:
                    f.write("vertex %g %g %g\n" % p)
                f.write("endloop\nendfacet\n")
            f.write("endsolid box\n")
        return path

    def drawn(self, img):
        """How many pixels are not the background, and how many shades they have."""
        seen, shades = 0, set()
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                c = img.pixelColor(x, y)
                if (c.red(), c.green(), c.blue()) != BG:
                    seen += 1
                    shades.add(c.red())
        return seen, len(shades)

    def test_binary_and_ascii(self):
        for path in (self.write_binary("box.stl"), self.write_ascii("box_ascii.STL")):
            img = open_dialog.stl_picture(path, 128)
            self.assertIsNotNone(img, path)
            seen, shades = self.drawn(img)
            self.assertGreater(seen, 400, path)  # the box fills a good part of the picture
            self.assertGreaterEqual(shades, 3, path)  # top and two sides lit differently
            if os.environ.get("INNCAD_SHOT"):
                img.save(os.environ["INNCAD_SHOT"])

    def test_obj_and_a_picture(self):
        path = os.path.join(self.dir, "box.obj")
        v = [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0), (0, 0, 6), (20, 0, 6), (20, 10, 6), (0, 10, 6)]
        with open(path, "w") as f:
            f.writelines("v %g %g %g\n" % p for p in v)
            f.write("f 1 4 3 2\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n")  # quads
        img = open_dialog.stl_picture(path, 128)
        self.assertIsNotNone(img)
        self.assertGreater(self.drawn(img)[0], 400)
        jpg = os.path.join(self.dir, "photo.png")
        img.save(jpg)
        p = open_dialog.Preview()
        p.show_file(jpg)
        self.assertTrue(p.has_picture())

    def test_preview_panel_shows_an_stl(self):
        p = open_dialog.Preview()
        p.show_file(self.write_binary("part.stl"))
        self.assertTrue(p.has_picture())
        p.show_file(os.path.join(self.dir, "missing.stl"))
        self.assertFalse(p.has_picture())

    def test_no_icon_provider_of_ours(self):
        d = open_dialog.OpenDialog(None, "Open", self.dir, "STL (*.stl)")
        self.assertFalse(hasattr(open_dialog, "Icons"))
        self.assertIsNotNone(d.preview)


if __name__ == "__main__":
    unittest.main()
