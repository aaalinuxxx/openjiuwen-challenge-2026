import unittest
import mylib

class Checks(unittest.TestCase):
    def test_overlap(self): self.assertEqual(mylib.occurrences('aaaa','aa'), 3)
    def test_empty(self): self.assertEqual(mylib.occurrences('abc',''), 0)
    def test_missing(self): self.assertEqual(mylib.occurrences('ab','abcd'), 0)
    def test_exact(self): self.assertEqual(mylib.occurrences('abc','abc'), 1)

if __name__ == '__main__': unittest.main()
