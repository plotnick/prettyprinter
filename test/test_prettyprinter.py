from __future__ import with_statement
import unittest
from cStringIO import StringIO
from format import format
from prettyprinter import *

class PrettyPrinterTest(unittest.TestCase):
    def ppEquals(self, result, width, pprint, *args):
        stringstream = StringIO()
        pp = PrettyPrinter(stream=stringstream, width=width)
        pprint(pp, *args)
        self.assertEqual(result, stringstream.getvalue())
        pp.close()
        stringstream.close()

    def ppFormatEquals(self, result, width, control, *args):
        stringstream = StringIO()
        pp = PrettyPrinter(stream=stringstream, width=width)
        format(pp, control, *args)
        self.assertEqual(result, stringstream.getvalue())
        pp.close()
        stringstream.close()

    def testLogicalBlock(self):
        control = "+ ~<Roads ~<~A, ~:_~A~:> ~:_ Town ~<~A~:>~:> +"
        roads = ["Elm", "Cottonwood"]
        town = ["Boston"]

        self.ppFormatEquals("""
+ Roads Elm, Cottonwood  Town Boston +"""[1:], 50, control, [roads, town])
        self.ppFormatEquals("""
+ Roads Elm, Cottonwood 
   Town Boston +"""[1:], 25, control, [roads, town])
        self.ppFormatEquals("""
+ Roads Elm, 
        Cottonwood 
   Town Boston +"""[1:], 21, control, [roads, town])

    def testIndentation(self):
        control = "~<(~;~A ~:I~A ~:_~A ~1I~_~A~;)~:>"
        defun = ["defun", "prod", "(x y)", "(* x y)"]

        self.ppFormatEquals("""
(defun prod (x y) (* x y))"""[1:], 50, control, defun)
        self.ppFormatEquals("""
(defun prod (x y) 
  (* x y))"""[1:], 25, control, defun)
        self.ppFormatEquals("""
(defun prod 
       (x y) 
  (* x y))"""[1:], 15, control, defun)

if __name__ == "__main__":
    unittest.main()
