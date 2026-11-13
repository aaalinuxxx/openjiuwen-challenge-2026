import unittest
import mylib

class Checks(unittest.TestCase):
    def test_touch(self): self.assertEqual(mylib.merge_intervals([(3,5),(1,3),(8,9)]), [(1,5),(8,9)])
    def test_nested(self): self.assertEqual(mylib.merge_intervals([(1,9),(2,3)]), [(1,9)])
    def test_empty(self): self.assertEqual(mylib.merge_intervals([]), [])
    def test_input(self):
        data = [(5,7),(1,2)]
        before = list(data)
        mylib.merge_intervals(data)
        self.assertEqual(data, before)

if __name__ == '__main__': unittest.main()
