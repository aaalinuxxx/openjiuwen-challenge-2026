import unittest
import mylib as m

class TestLib(unittest.TestCase):
    def test_0(self):
        self.assertEqual(m.total([2, 4, 6]), 12)
    def test_1(self):
        self.assertEqual(m.total([2, 4, 6]), 100)

if __name__ == '__main__': unittest.main()
