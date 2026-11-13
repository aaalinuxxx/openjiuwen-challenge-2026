import unittest
from mylib import *

class Tests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(rotate_right([],5),[])
        self.assertEqual(rotate_right([1,2,3],1),[3,1,2])
        self.assertEqual(rotate_right([1,2,3],-1),[2,3,1])
        self.assertEqual(rotate_right([1,2,3],7),[3,1,2])
        a=[1,2];b=rotate_right(a,0)
        self.assertIsNot(a,b)
        self.assertEqual(a,[1,2])

if __name__=='__main__':unittest.main()
