import unittest
from format import format, FormatError

class FormatTest(unittest.TestCase):
    def formatEquals(self, result, control, *args):
        self.assertEqual(result, format(None, control, *args))

    def formatRaises(self, exc, control, *args):
        self.assertRaises(exc, format, None, control, *args)

    def testRadix(self):
        self.formatEquals("1101", "~,,' ,4:B", 13)
        self.formatEquals("1 0001", "~,,' ,4:B", 17)
        self.formatEquals("0000 1101 0000 0101", "~19,0,' ,4:B", 3333)
        self.formatEquals("-000 1101 0000 0101", "~19,0,' ,4:B", -3333)
        #self.formatEquals("1 22", "~3,,,' ,2:R", 17)
        self.formatEquals("6|55|35", "~,,'|,2:D", 0xFFFF)

    def testTabulate(self):
        self.formatEquals(" foo", "~Tfoo")
        self.formatEquals("        foo", "~0,8Tfoo")
        self.formatEquals("foobar  foo", "foobar~0,8Tfoo")
        self.formatEquals("foobar  foo", "foobar~2,8@Tfoo")
        self.formatEquals("foobar          foo", "foobar~3,8@Tfoo")

    def testConditional(self):
        self.formatEquals("Zero", "~0[Zero~;One~:;Other~]")
        self.formatEquals("One", "~1[Zero~;One~:;Other~]")
        self.formatEquals("Other", "~2[Zero~;One~:;Other~]")
        self.formatEquals("Other", "~99[Zero~;One~:;Other~]")

        self.formatEquals("False", "~:[False~;True~]", False)
        self.formatEquals("True", "~:[False~;True~]", True)

        self.formatEquals("ab", "~@[~A~]~A", "a", "b")
        self.formatEquals("a", "~@[~A~]~A", False, "a")

    def testIteration(self):
        # Normal iteration.
        self.formatEquals("The winners are: Fred Harry Jill.",
                          "The winners are:~{ ~A~}.", ["Fred", "Harry", "Jill"])
        # Force exactly one iteration.
        self.formatEquals("The winners are: Fred.",
                          "The winners are:~1{ ~A~}.", ["Fred", "Harry"])
        # Empty body: use arg as control string.
        self.formatEquals("The winners are: Fred Harry Jill.",
                          "The winners are:~{~}.",
                          " ~A", ["Fred", "Harry", "Jill"])
        # Take the param before a control string arg.
        self.formatEquals("The winners are: Fred.",
                          "The winners are:~V{~}.",
                           1, " ~A", ["Fred", "Harry", "Jill"])
        # Empty list.
        self.formatEquals("The winners are:.",
                          "The winners are:~{ ~A~}.", [])
        # Force one iteration, even with empty list.
        self.formatEquals("The winners are: Fred.",
                          "The winners are:~{ Fred~:}.", [])
        # Variable max iterations.
        self.formatEquals("The winners are: 1 2.",
                          "The winners are:~V{ ~D~}.", 2, [1, 2, 3, 4])
        # Iterate over list of sublists.
        self.formatEquals("Pairs: <a,1> <b,2> <c,3>.",
                          "Pairs:~:{ <~A,~D>~}.", [("a", 1), ("b", 2), ("c", 3)])
        # Iterate over args.
        self.formatEquals("Pairs: <a,1> <b,2> <c,3>.",
                          "Pairs:~@{ <~A,~D>~}.", "a", 1, "b", 2, "c", 3)
        # Iterate over args as sublists.
        self.formatEquals("Pairs: <a,1> <b,2> <c,3>.",
                          "Pairs:~:@{ <~A,~D>~}.", ("a", 1), ("b", 2), ("c", 3))

    def testPlural(self):
        pluralstr = "~D tr~:@P/~D win~:P"
        self.formatEquals("7 tries/1 win", pluralstr, 7, 1)
        self.formatEquals("1 try/0 wins", pluralstr, 1, 0)
        self.formatEquals("1 try/3 wins", pluralstr, 1, 3)

    def testEscape(self):
        donestr = "Done.~^ ~D warning~:P.~^ ~D error~:P."
        self.formatEquals("Done.", donestr)
        self.formatEquals("Done. 3 warnings.", donestr, 3)
        self.formatEquals("Done. 1 warning. 5 errors.", donestr, 1, 5)

        self.formatRaises(FormatError, "~D~:^~D", 1, 2, 3)

        self.formatEquals("a...b", "~:{~@?~:^...~}", [["a"], ["b"]])

        foods = [["hot", "dog"],
                 ["hamburger"],
                 ["ice", "cream"],
                 ["french", "fries"]]
        self.formatEquals("/hot .../hamburger/ice .../french ...",
                          "~:{/~A~^ ...~}", foods)
        self.formatEquals("/hot .../hamburger .../ice .../french",
                          "~:{/~A~:^ ...~}", foods)
        self.formatEquals("/hot .../hamburger",
                          "~:{/~A~#:^ ...~}", foods)

    def testItems(self):
        """Exercises conditionals, iteration, and escapes."""
        items = "Items:~#[ none~; ~S~; ~S and ~S~:;~@{~#[~; and~] ~S~^,~}~]."
        self.formatEquals("Items: none.", items)
        self.formatEquals("Items: 'FOO'.", items, "FOO")
        self.formatEquals("Items: 'FOO' and 'BAR'.", items, "FOO", "BAR")
        self.formatEquals("Items: 'FOO', 'BAR', and 'BAZ'.",
                          items, "FOO", "BAR", "BAZ")
        self.formatEquals("Items: 'FOO', 'BAR', 'BAZ', and 'QUUX'.",
                          items, "FOO", "BAR", "BAZ", "QUUX")

    def testRecursive(self):
        self.formatEquals("<Foo 5> 7", "~? ~D", "<~A ~D>", ["Foo", 5], 7)
        self.formatEquals("<Foo 5> 7", "~? ~D", "<~A ~D>", ["Foo", 5, 14], 7)
        self.formatEquals("<Foo 5> 7", "~@? ~D", "<~A ~D>", "Foo", 5, 7)
        self.formatEquals("<Foo 5> 14", "~@? ~D", "<~A ~D>", "Foo", 5, 14, 7)

if __name__ == "__main__":
    unittest.main()
