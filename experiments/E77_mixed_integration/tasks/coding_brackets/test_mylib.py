import unittest
import mylib

class Checks(unittest.TestCase):
    def test_nested(self): self.assertTrue(mylib.balanced('a{b[c(d)]}'))
    def test_crossed(self): self.assertFalse(mylib.balanced('([)]'))
    def test_unclosed(self): self.assertFalse(mylib.balanced('['))
    def test_extra(self): self.assertFalse(mylib.balanced(']'))
    def test_empty(self): self.assertTrue(mylib.balanced(''))

if __name__ == '__main__': unittest.main()
