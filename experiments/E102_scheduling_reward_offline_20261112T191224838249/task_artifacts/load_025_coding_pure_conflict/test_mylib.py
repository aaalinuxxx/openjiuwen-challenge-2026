import unittest
import mylib

class Checks(unittest.TestCase):
    def test_first(self): self.assertEqual(mylib.f(7), 3)
    def test_second(self): self.assertEqual(mylib.f(7), 4)

if __name__ == '__main__': unittest.main()
