import unittest
import mylib as m

class TestLib(unittest.TestCase):
    def test_0(self):
        self.assertEqual(m.average([-15, 4, -14, 2]), -5.75)
    def test_1(self):
        self.assertEqual(m.average([]), 0)
    def test_2(self):
        self.assertEqual(m.average([7]), 7)

if __name__ == '__main__': unittest.main()
