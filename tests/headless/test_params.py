import unittest

import FreeCAD as App
from incad.core import params

GROUP = "User parameter:BaseApp/Preferences/Mod/InCadTest"


class ParamsTest(unittest.TestCase):
    def test_snapshot_write_restore(self):
        p = App.ParamGet(GROUP)
        p.SetBool("Flag", True)
        p.SetUnsigned("Color", 0x112233FF)
        snap = params.snapshot(GROUP, {"Flag": "Bool", "Color": "Unsigned", "New": "String"})
        self.assertEqual(snap["Flag"], ["Bool", True, True])
        self.assertEqual(snap["New"], ["String", False, None])
        params.write(GROUP, {"Flag": ("Bool", False), "Color": ("Unsigned", 0xAABBCCFF), "New": ("String", "x")})
        self.assertFalse(p.GetBool("Flag", True))
        params.restore(GROUP, snap)
        self.assertTrue(p.GetBool("Flag", False))
        self.assertEqual(p.GetUnsigned("Color", 0), 0x112233FF)
        names = {c[1] for c in (p.GetContents() or [])}
        self.assertNotIn("New", names)


class GroupSnapshotTest(unittest.TestCase):
    def test_whole_group_bools_restored(self):
        group = GROUP + "/Toolbars"
        p = App.ParamGet(group)
        p.SetBool("File", True)
        p.SetBool("Edit", False)
        snap = params.snapshot_group(group)
        p.SetBool("File", False)
        p.SetBool("Edit", True)
        p.SetBool("Added", False)
        params.restore(group, snap)
        self.assertTrue(p.GetBool("File", False))
        self.assertFalse(p.GetBool("Edit", True))
        self.assertFalse(p.GetBool("Added", True))  # entries created later are left alone
