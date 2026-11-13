import unittest
from mylib import compress
class T(unittest.TestCase):
    def test_all(self):
        self.assertEqual(compress(''),'')
        self.assertEqual(compress('aaabbcaa'),'abca')
        self.assertEqual(compress('abab'),'abab')
if __name__=="__main__":unittest.main()
