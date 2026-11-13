import unittest
from mylib import *

class Tests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(run_lengths([]),[])
        self.assertEqual(run_lengths([2,2,1,2]),[(2,2),(1,1),(2,1)])
        self.assertEqual(run_lengths(['a','a','b']),[('a',2),('b',1)])
        a=[3,3,4];before=a[:];run_lengths(a)
        self.assertEqual(a,before)

if __name__=='__main__':unittest.main()
