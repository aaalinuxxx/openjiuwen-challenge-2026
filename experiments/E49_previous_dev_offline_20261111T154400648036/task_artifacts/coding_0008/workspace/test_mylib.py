import unittest
import mylib as m

class TestLib(unittest.TestCase):
    def test_0(self):
        self.assertEqual(m.stable_unique([10, -14, 10]), [10, -14])
    def test_1(self):
        self.assertEqual(m.stable_unique([]), [])
    def test_2(self):
        self.assertEqual(m.stable_unique([3, 3]), [3])

if __name__ == '__main__': unittest.main()
