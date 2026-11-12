import unittest
from mylib import f
class Tests(unittest.TestCase):
    def test_a(self):self.assertEqual(f(-1),0)
    def test_b(self):self.assertEqual(f(-1),2)
if __name__=='__main__':unittest.main()
