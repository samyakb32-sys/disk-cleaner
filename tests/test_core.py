import os
import tempfile
import threading
import unittest

from diskmover import core


def touch(path, data="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(data)


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.docs = os.path.join(self.tmp, "home", "Documents")
        self.dest = os.path.join(self.tmp, "D", "backup")
        touch(os.path.join(self.docs, "a.txt"))
        touch(os.path.join(self.docs, "sub", "b.txt"))
        touch(os.path.join(self.docs, "desktop.ini"))
        touch(os.path.join(self.docs, "AppData", "secret.dat"))

    def test_scan_skips_protected(self):
        names = sorted(os.path.basename(i.src) for i in core.scan([self.docs], self.dest))
        self.assertEqual(names, ["a.txt", "b.txt"])

    def test_move_and_undo(self):
        items = list(core.scan([self.docs], self.dest))
        moved, failed = core.execute(items, self.dest)
        self.assertEqual((len(moved), failed), (2, []))
        self.assertFalse(os.path.exists(os.path.join(self.docs, "a.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.dest, "Documents", "sub", "b.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.docs, "AppData", "secret.dat")))
        restored, failed = core.undo(self.dest)
        self.assertEqual((restored, failed), (2, []))
        self.assertTrue(os.path.exists(os.path.join(self.docs, "sub", "b.txt")))

    def test_name_collision_keeps_both(self):
        touch(os.path.join(self.dest, "Documents", "a.txt"), "old")
        core.execute(list(core.scan([self.docs], self.dest)), self.dest)
        self.assertTrue(os.path.exists(os.path.join(self.dest, "Documents", "a (1).txt")))

    def test_dest_inside_source_rejected(self):
        self.assertIsNotNone(core.validate([self.docs], os.path.join(self.docs, "out")))

    def test_dest_not_rescanned(self):
        dest = os.path.join(self.docs, "..", "Documents2")
        touch(os.path.join(self.docs, "out", "z.txt"))
        names = [os.path.basename(i.src) for i in core.scan([self.docs], os.path.join(self.docs, "out"))]
        self.assertNotIn("z.txt", names)

    def test_cancel(self):
        ev = threading.Event(); ev.set()
        self.assertEqual(list(core.scan([self.docs], self.dest, ev)), [])


if __name__ == "__main__":
    unittest.main()
