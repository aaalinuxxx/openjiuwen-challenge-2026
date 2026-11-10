import unittest
import mylib as m

class TestLib(unittest.TestCase):
    def test_total(self):
        self.assertEqual(m.total([1, 2, 3]), 6)

    def test_conflict_a(self):
        self.assertEqual(m.average([2, 4, 6]), 4)

    def test_conflict_b(self):
        self.assertEqual(m.average([2, 4, 6]), 100)

if __name__ == '__main__':
    unittest.main()
