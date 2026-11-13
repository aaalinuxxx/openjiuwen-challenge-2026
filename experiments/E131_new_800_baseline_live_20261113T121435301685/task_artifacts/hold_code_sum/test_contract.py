import unittest
from mylib import sum_even
class T(unittest.TestCase):
    def test_all(self):
        self.assertEqual(sum_even([]),0)
        self.assertEqual(sum_even([1, 2, 4, 7]),6)
        self.assertEqual(sum_even([-2, -3, 6]),4)
if __name__=="__main__":unittest.main()
