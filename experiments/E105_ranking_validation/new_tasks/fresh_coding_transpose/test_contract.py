import unittest
from mylib import *

class Tests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(transpose([]),[])
        self.assertEqual(transpose([[1,2,3],[4,5,6]]),[[1,4],[2,5],[3,6]])
        self.assertEqual(transpose([[7],[8]]),[[7,8]])
        a=[[1,2],[3,4]];before=[r[:] for r in a];transpose(a)
        self.assertEqual(a,before)

if __name__=='__main__':unittest.main()
