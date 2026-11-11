import unittest
import mylib as m

class TestLib(unittest.TestCase):
    def test_0(self):
        self.assertEqual(m.rotate([21, 17, 9, 13]), [13, 21, 17, 9])
    def test_1(self):
        self.assertEqual(m.rotate([]), [])
    def test_2(self):
        self.assertEqual(m.rotate([9]), [9])

if __name__ == '__main__': unittest.main()
