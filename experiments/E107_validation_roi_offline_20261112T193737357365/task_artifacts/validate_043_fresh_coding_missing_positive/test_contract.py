import unittest
from mylib import *

class Tests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(first_missing_positive([]),1)
        self.assertEqual(first_missing_positive([1,2,0]),3)
        self.assertEqual(first_missing_positive([3,4,-1,1]),2)
        self.assertEqual(first_missing_positive([1,1,2,2]),3)
        a=[2,1];before=a[:];first_missing_positive(a)
        self.assertEqual(a,before)

if __name__=='__main__':unittest.main()
