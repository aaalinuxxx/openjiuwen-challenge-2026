import unittest
import mylib

class Checks(unittest.TestCase):
    def test_sequence(self):
        c = mylib.Counter()
        self.assertEqual(c.next(), 1)
        self.assertEqual(c.next(), 2)
    def test_independent(self):
        a, b = mylib.Counter(), mylib.Counter()
        a.next()
        self.assertEqual(b.next(), 1)

if __name__ == '__main__': unittest.main()
