import unittest
from mylib import solve
class Tests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(solve([]),[])
        self.assertEqual(solve([2, -3, 7]),[2, -1, 6])
        self.assertEqual(solve([0, 0]),[0, 0])
        a=[3,1,3,2]; before=a[:]; solve(a); self.assertEqual(a,before)
if __name__=='__main__':unittest.main()
