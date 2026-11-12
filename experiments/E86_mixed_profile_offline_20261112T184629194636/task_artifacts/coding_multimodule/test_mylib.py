import unittest
import mylib

class Checks(unittest.TestCase):
    def test_edge(self): self.assertEqual(mylib.keep([4,5,6]), [5,6])
    def test_empty(self): self.assertEqual(mylib.keep([]), [])
    def test_import(self):
        import a_settings
        self.assertEqual(a_settings.threshold(), 5)
        self.assertIs(mylib.threshold, a_settings.threshold)

if __name__ == '__main__': unittest.main()
