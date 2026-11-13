import unittest
from mylib import solve
class Tests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(solve([]),[])
        self.assertEqual(solve([1, 3, 2, 4, 5, 5]),[2, 3, 1])
        self.assertEqual(solve([4, 3, 2]),[1, 1, 1])
        self.assertEqual(solve([2]),[1])
        a=[3,1,3,2]; before=a[:]; solve(a); self.assertEqual(a,before)
if __name__=='__main__':unittest.main()
