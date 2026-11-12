import unittest
from mylib import *

class Tests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(stable_unique([]),[])
        self.assertEqual(stable_unique([3,1,3,2,1]),[3,1,2])
        self.assertEqual(stable_unique(['b','a','b',None]),['b','a',None])
        a=[2,1,2];before=a[:];stable_unique(a)
        self.assertEqual(a,before)

if __name__=='__main__':unittest.main()
