import unittest
from mylib import solve
class Tests(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(solve([]),[])
        self.assertEqual(solve([2, 1, 2, 4, 3]),[4, 2, 4, None, None])
        self.assertEqual(solve([3, 3, 3]),[None, None, None])
        self.assertEqual(solve([-3, -1, -2]),[-1, None, None])
        a=[3,1,3,2]; before=a[:]; solve(a); self.assertEqual(a,before)
if __name__=='__main__':unittest.main()
