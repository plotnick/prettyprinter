from __future__ import with_statement
import unittest
from cStringIO import StringIO
from format import format
from prettyprinter import *
from bindings import bindings
import printervars

class PrettyPrinterTest(unittest.TestCase):
    def ppEquals(self, result, obj, *args, **kwargs):
        stringstream = StringIO()
        pp = PrettyPrinter(stringstream, *args, **kwargs)
        pp.pprint(obj)
        pp.close()
        self.assertEqual(result, stringstream.getvalue())
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

    def testPrintLevel(self):
        levels = ["#",
                  "(1, #)",
                  "(1, (2, #))",
                  "(1, (2, (3, #)))",
                  "(1, (2, (3, (4, #))))",
                  "(1, (2, (3, (4, (5, #)))))",
                  "(1, (2, (3, (4, (5, (6,))))))",
                  "(1, (2, (3, (4, (5, (6,))))))"]
        a = (1, (2, (3, (4, (5, (6,))))))
        for i in range(8):
            with bindings(printervars, print_level=i):
                self.ppEquals(levels[i], a)

    def testPrintLength(self):
        lengths = ["(...)",
                   "(1, ...)",
                   "(1, 2, ...)",
                   "(1, 2, 3, ...)",
                   "(1, 2, 3, 4, ...)",
                   "(1, 2, 3, 4, 5, ...)",
                   "(1, 2, 3, 4, 5, 6)",
                   "(1, 2, 3, 4, 5, 6)"]
        a = (1, 2, 3, 4, 5, 6)
        for i in range(7):
            with bindings(printervars, print_length=i):
                self.ppEquals(lengths[i], a)

    def testPrintLevelLength(self):
        levelLengths = {
            (0, 1): "#",
            (1, 1): "(if ...)",
            (1, 2): "(if # ...)",
            (1, 3): "(if # # ...)",
            (1, 4): "(if # # #)",
            (2, 1): "(if ...)",
            (2, 2): "(if (member x ...) ...)",
            (2, 3): "(if (member x y) (+ # 3) ...)",
            (3, 2): "(if (member x ...) ...)",
            (3, 3): "(if (member x y) (+ (car x) 3) ...)",
            (3, 4): "(if (member x y) (+ (car x) 3) (foo (a b c d ...)))"
        }
        sexp = ("if", ("member", "x", "y"), ("+", ("car", "x"), 3),
                ("foo", ("a", "b", "c", "d", "Baz")))
        for (level, length) in [(0, 1), (1, 2), (1, 2), (1, 3), (1, 4),
                                (2, 1), (2, 2), (2, 3), (3, 2), (3, 3), (3, 4)]:
            with bindings(printervars,
                          print_pretty=True, print_escape=False,
                          print_level=level, print_length=length):
                s = format(None, "~W", sexp)
                self.assertEqual(levelLengths[(level, length)],
                                 s.replace(",", ""))

if __name__ == "__main__":
    unittest.main()
