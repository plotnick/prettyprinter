from __future__ import with_statement

import sys
from cStringIO import StringIO
from math import log10
from charpos import CharposStream
from prettyprinter import PrettyPrinter

__all__ = ["Formatter", "format"]

class FormatError(StandardError):
    pass

class UpAndOut(Exception):
    pass

class UpUpAndOut(Exception):
    pass

class Arguments(object):
    def __init__(self, args, outer=None):
        self.args = args
        self.outer = outer
        self.len = len(self.args)
        self.cur = 0
        self.empty = (self.len == 0)

    def __len__(self): return self.len
    def __getitem__(self, key): return self.args[key]
    def __iter__(self): return self

    def next(self):
        if self.empty:
            raise StopIteration
        cur = self.cur
        arg = self.args[cur]
        cur += 1
        self.cur = cur
        self.empty = (cur == self.len)
        return arg

    def prev(self):
        cur = self.cur
        if cur == 0:
            raise StopIteration
        cur -= 1
        arg = self.args[cur]
        self.cur = cur
        self.empty = False
        return arg

    def peek(self, n=0):
        return self.args[self.cur + n]

    def goto(self, n):
        if n < 0 or n >= self.len:
            raise IndexError("index %d is out of bounds" % n)
        self.cur = n
        empty = False

    @property
    def remaining(self):
        return self.len - self.cur

class Modifiers:
    colon = frozenset([":"])
    atsign = frozenset(["@"])
    both = frozenset([":@"])
    all = colon | atsign | both

class Directive(object):
    variable_parameter = object()
    remaining_parameter = object()
    modifiers_allowed = None
    need_charpos = False

    def __init__(self, params, colon, atsign, control, start, end, parent=None):
        if (colon or atsign) and self.modifiers_allowed is None:
            raise FormatError("neither colon nor at-sign allowed "
                              "for this directive")
        elif (colon and atsign) and ":@" not in self.modifiers_allowed:
            raise FormatError("cannot specify both colon and at-sign")
        elif colon and ":" not in self.modifiers_allowed:
            raise FormatError("colon not allowed for this directive")
        elif atsign and "@" not in self.modifiers_allowed:
            raise FormatError("at-sign not allowed for this directive")

        self.params = params; self.colon = colon; self.atsign = atsign
        self.control = control; self.start = start; self.end = end
        self.parent = parent

    def __str__(self): return self.control[self.start:self.end]
    def __len__(self): return self.end - self.start

    def param(self, n, args, default=None):
        if n < len(self.params):
            p = self.params[n]
            if p is Directive.variable_parameter: p = args.next()
            elif p is Directive.remaining_parameter: p = args.remaining
            return p if p is not None else default
        else:
            return default

    def governed_by(self, cls):
        """If an instance of cls appears anywhere in the chain of parents from
        this instance to the root, return that instance, or None otherwise."""
        parent = self.parent
        while parent:
            if isinstance(parent, cls):
                return parent
            parent = parent.parent
        return None

class DelimitedDirective(Directive):
    """Delimited directives, such as conditional expressions and
    justifications, are composed of an opening delimiter, zero or more
    clauses separated by a separator, and a closing delimiter.

    Subclasses should define a class attribute, delimiter, that specifies
    the class of the closing delimiter.  Instances will have that attribute
    set to the instance of that class actually encountered."""

    delimiter = None

    def __init__(self, *args):
        super(DelimitedDirective, self).__init__(*args)
        self.clauses = [[]]
        self.separators = []

    def append(self, x):
        if isinstance(x, Separator):
            self.separators.append(x)
            self.clauses.append([])
        elif isinstance(x, self.delimiter):
            self.delimiter = x
            self.delimited()
        else:
            self.clauses[len(self.separators)].append(x)
        self.end = x.end if isinstance(x, Directive) else (self.end + len(x))

    def delimited(self):
        """Called when the complete directive, including the delimiter, has
        been parsed."""

        # Most delimited directives need charpos if any of their clauses do.
        self.need_charpos = any([d.need_charpos for c in self.clauses \
                                                for d in c \
                                     if isinstance(d, Directive)])

# Basic Output

class ConstantChar(Directive):
    def __new__(cls, params, colon, atsign, *args):
        if colon or atsign:
            raise FormatError("neither colon nor at-sign allowed "
                              "for this directive")
        if not params:
            return cls.character
        elif params and isinstance(params[0], int):
            return cls.character * params[0]
        else:
            return super(ConstantChar, cls).__new__(cls, params, colon, atsign,
                                                    *args)

    def format(self, stream, args):
        stream.write(self.character * self.param(0, args, 1))

class Newline(ConstantChar):
    character = "\n"

class FreshLine(Directive):
    need_charpos = True

    def format(self, stream, args):
        n = self.param(0, args, 1)
        if n > 0:
            try:
                stream.fresh_line()
                n -= 1
                while n > 0:
                    stream.terpri()
                    n -= 1
            except AttributeError:
                stream.write("\n" * n)                    

class Page(ConstantChar):
    character = "\f"

class Tilde(ConstantChar):
    character = "~"

# Radix Control

digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def convert(n, radix):
    """Yield the digits of the non-negative number n in the given radix."""
    def le_digits(n, radix):
        while n > 0:
            yield digits[n % radix]
            n /= radix
    if radix < 2 or radix > 36:
        raise ValueError("radix out of range")
    return reversed(tuple(le_digits(n, radix)))

roman_numerals = ["M", 2, "D", 5, "C", 2, "L", 5, "X", 2, "V", 5, "I"]

def roman_int(n, oldstyle=False):
    """Yield the Roman numeral representation of n.  This routine is a
    straightforward translation of the code from section 69 of TeX82, where
    it is prefaced by the following comment:

        Readers who like puzzles might enjoy trying to figure out how
        this tricky code works; therefore no explanation will be given.
        Notice that 1990 yields MCMXC, not MXM.

    The only substantive change to the algorithm is the addition of the
    old-style flag."""
    if n < 1 or n > (4999 if oldstyle else 3999):
        raise ValueError("integer cannot be expressed as Roman numerals")

    # j & k are mysterious indices into roman_numerals;
    # u & v are mysterious numbers
    j = 0; v = 1000
    while True:
        while n >= v:
            yield roman_numerals[j]; n -= v
        if n <= 0: return   # nonpositive input produces no output
        k = j + 2; u = v / roman_numerals[k - 1]
        if roman_numerals[k - 1] == 2:
            k += 2; u /= roman_numerals[k - 1]
        if n + u >= v and not oldstyle:
            yield roman_numerals[k]; n += u
        else:
            j += 2; v /= roman_numerals[j - 1]

# English ordinal & cardinal conversion code contributed by Richard
# M. Kreuter <kreuter@progn.net>.

cardinals = ["zero", "one", "two" , "three", "four",
             "five", "six", "seven", "eight", "nine",
             "ten", "eleven", "twelve", "thirteen", "fourteen",
             "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]

ordinals = ["zeroth", "first", "second", "third", "fourth",
            "fifth", "sixth", "seventh", "eighth", "ninth",
            "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth",
            "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth"]

tenstems = ["", "ten", "twent", "thirt", "fourt", "fift",
            "sixt", "sevent", "eight", "ninet"]

ten_cubes = ["", "thousand", "million", "billion", "trillion",
             "quadrillion", "quintillion", "sextillion", "septillion",
             "octillion", "nonillion"]

def itoe(n, ordinal):
    if n < 0:
        s = "negative "
        n = abs(n)
    else:
        s = ""

    if ordinal:
        table = ordinals
        osuff = "th"
        tsuff0 = "ieth"
    else:
        table = cardinals
        osuff = ""
        tsuff0 = "y"
    tsuff1 = "y"
    if n < 1000:
        if n >= 100:
            return s + "%s hundred" % itoc(n/100) + \
                (osuff if n % 100 == 0 else (" " + itoe(n % 100, ordinal)))
        else:
            if n < 20:
                return s + table[n]
            else:
                ones = n % 10
                return s + tenstems[n/10] + \
                    (tsuff0 if ones == 0 else (tsuff1 + "-" + table[ones]))

    v = int(log10(n)) / 3
    u = 1000 ** v
    while v >= 0:
        q = n / u
        if q != 0:
            s += itoe(q, ordinal and n < 1000)
            if v >= len(ten_cubes):
                s += " times ten to the %s power plus" % (itoo(3*v))
            elif ten_cubes[v]:
                s += " " + ten_cubes[v]
            n %= u
            if n == 0:
                if v > 0: s += osuff
            else:
                if n >= 100 and v < len(ten_cubes): s += ","
                s += " "
        v -= 1
        u /= 1000
    return s

def itoo(n):
    return itoe(n, True)

def itoc(n):
    return itoe(n, False)

class Numeric(Directive):
    """Base class for numeric (radix control) directives."""

    modifiers_allowed = Modifiers.all

    def format(self, stream, args):
        def commafy(s, commachar, comma_interval):
            """Add commachars between groups of comma_interval digits."""
            first = len(s) % comma_interval
            a = [s[0:first]] if first > 0 else []
            for i in range(first, len(s), comma_interval):
                a.append(s[i:i + comma_interval])
            return commachar.join(a)

        i = 0
        if self.radix:
            radix = self.radix
        else:
            radix = int(self.param(0, args, 0)); i += 1
        mincol = int(self.param(i, args, 0)); i += 1
        padchar = str(self.param(i, args, " ")); i += 1
        commachar = str(self.param(i, args, ",")); i += 1
        comma_interval = int(self.param(i, args, 3)); i += 1

        n = args.next()
        s = self.convert(abs(n), radix)
        sign = ("+" if n >= 0 else "-") if self.atsign else \
               ("-" if n < 0 else "")
        if self.colon:
            if padchar == "0" and mincol > len(s) + len(sign):
                # We pad with zeros first so that they can be commafied,
                # too (cf. CLiki Issue FORMAT-RADIX-COMMACHAR).  But in
                # order to figure out how many to add, we need to solve a
                # little constraint problem.
                def col(n):
                    return n + (n-1)/comma_interval + len(sign)
                width = -1
                for i in range(len(s), mincol):
                    if col(i) == mincol:
                        # exact fit
                        width = i
                        break
                    elif col(i) > mincol:
                        # too big
                        width = i - 1
                        break
                assert width > 0, "couldn't find a width"
                s = s.rjust(width, padchar)

                # If we're printing a sign, and the width that we chose
                # above is a multiple of comma_interval, we'll need (at
                # most one) extra space to get up to mincol.
                padchar = " "

            s = commafy(s, commachar, comma_interval)
        stream.write((sign + s).rjust(mincol, padchar))

class Radix(Numeric):
    radix = None

    def __init__(self, *args):
        super(Radix, self).__init__(*args)
        if not self.params:
            self.format = self.old_roman if self.colon and self.atsign \
                                         else self.roman if self.atsign \
                                         else self.ordinal if self.colon \
                                         else self.cardinal

    def convert(self, n, radix):
        return "".join(convert(n, radix))

    def roman(self, stream, args):
        stream.write("".join(roman_int(args.next())))

    def old_roman(self, stream, args):
        stream.write("".join(roman_int(args.next(), True)))

    def ordinal(self, stream, args):
        stream.write(itoo(args.next()))

    def cardinal(self, stream, args):
        stream.write(itoc(args.next()))

class Decimal(Numeric):
    radix = 10

    def convert(self, n, radix):
        return "%d" % n

class Binary(Numeric):
    radix = 2
    octal_digits = ["000", "001", "010", "011", "100", "101", "110", "111"]

    def convert(self, n, radix):
        return "".join(self.octal_digits[int(digit)] \
                           for digit in "%o" % n).lstrip("0")

class Octal(Numeric):
    radix = 8

    def convert(self, n, radix):
        return "%o" % n

class Hexadecimal(Numeric):
    radix = 16

    def convert(self, n, radix):
        return "%X" % n

# Printer Operations

class Aesthetic(Directive):
    modifiers_allowed = Modifiers.all

    def format(self, stream, args):
        mincol = self.param(0, args, 0)
        colinc = self.param(1, args, 1)
        minpad = self.param(2, args, 0)
        padchar = self.param(3, args, " ")

        # The string methods l/rjust don't support a colinc or minpad.
        if colinc != 1: raise FormatError("colinc parameter must be 1")
        if minpad != 0: raise FormatError("minpad parameter must be 0")

        a = args.next()
        s = "[]" if self.colon and a is None else str(a)
        stream.write(s.rjust(mincol, padchar) if self.atsign else \
                     s.ljust(mincol, padchar))

class Standard(Directive):
    modifiers_allowed = Modifiers.all

    def format(self, stream, args):
        stream.write(repr(args.next()))

class Write(Directive):
    modifiers_allowed = Modifiers.all

    def format(self, stream, args):
        arg = args.next()
        try:
            stream.pprint(arg)
        except AttributeError:
            stream.write(repr(arg))

# Pretty Printer Operations

class ConditionalNewline(Directive):
    modifiers_allowed = Modifiers.all

    def format(self, stream, args):
        stream.newline(mandatory=(self.colon and self.atsign), fill=self.colon)

class LogicalBlock(DelimitedDirective):
    # NOTE: Instances of this class are never created directly; the
    # delimiter method of the Justification class changes the class
    # of instances delimited with "~:>".

    def delimited(self):
        super(LogicalBlock, self).delimited()

        # Note: with the colon modifier, the prefix & suffix default to
        # square, not round brackets; this is Python, not Lisp.
        self.prefix = "[" if self.colon else ""
        self.suffix = "]" if self.colon else ""
        if len(self.clauses) == 0:
            self.body = []
        elif len(self.clauses) == 1:
            (self.body,) = self.clauses
        elif len(self.clauses) == 2:
            ((self.prefix,), self.body) = self.clauses
        elif len(self.clauses) == 3:
            ((self.prefix,), self.body, (self.suffix,)) = self.clauses
        else:
            raise FormatError("too many segments for ~~<...~~:>")

    def format(self, stream, args):
        if not isinstance(stream, PrettyPrinter):
            stream = PrettyPrinter(stream=stream)
        with stream.logical_block(None,
                                  prefix=str(self.prefix),
                                  suffix=str(self.suffix)):
            try:
                apply_directives(stream,
                                 self.body,
                                 args if self.atsign else Arguments(args.next()))
            except UpAndOut:
                pass

class Indentation(Directive):
    modifiers_allowed = Modifiers.colon

    def format(self, stream, args):
        stream.indent(offset=int(self.param(0, args, 0)), relative=self.colon)

# Layout Control

class Tabulate(Directive):
    modifiers_allowed = Modifiers.all
    need_charpos = True

    def format(self, stream, args):
        def ceiling(a, b):
            q, r = divmod(a, b)
            return (q + 1) if r else q

        def output_spaces(stream, n):
            stream.write(" " * n)

        if self.colon:
            raise FormatError("%s not yet supported" % self)
        elif self.atsign:
            # relative tabulation
            colrel = int(self.param(0, args, 1))
            colinc = int(self.param(1, args, 1))
            try:
                cur = stream.charpos
                output_spaces(stream,
                              colinc * ceiling(cur + colrel, colinc) - cur)
            except AttributeError:
                output_spaces(stream, colrel)

        else:
            # absolute tabulation
            colnum = int(self.param(0, args, 1))
            colinc = int(self.param(1, args, 1))
            try:
                cur = stream.charpos
                if cur < colnum:
                    output_spaces(stream, colnum - cur)
                elif colinc > 0:
                    output_spaces(stream, colinc - ((cur - colnum) % colinc))
            except AttributeError:
                stream.write("  ")

class EndJustification(Directive):
    modifiers_allowed = Modifiers.colon

class Justification(DelimitedDirective):
    modifiers_allowed = Modifiers.all
    delimiter = EndJustification

    def delimited(self):
        if self.delimiter.colon:
            # Blame Dick Waters.
            self.__class__ = LogicalBlock
            self.delimited()
        else:
            super(Justification, self).delimited()

    def format(self, stream, args):
        raise FormatError("justification not yet implemented")

# Control-Flow Operations

class GoTo(Directive):
    modifiers_allowed = Modifiers.all

    def format(self, stream, args):
        if self.atsign:
            args.goto(self.param(0, args, 0))
        else:
            for i in range(self.param(0, args, 1)):
                if self.colon: args.prev()
                else: args.next()

class EndConditional(Directive):
    pass

class Conditional(DelimitedDirective):
    modifiers_allowed = Modifiers.all
    delimiter = EndConditional

    def delimited(self):
        if self.colon:
            if len(self.clauses) != 2:
                raise FormatError("must specify exactly two sections")
        elif self.atsign:
            if len(self.clauses) != 1:
                raise FormatError("can only specify one section")
        else:
            if len(self.separators) > 1 and \
                    any([s.colon for s in self.separators[0:-1]]):
                raise FormatError("only the last ~~; may have a colon")

    def format(self, stream, args):
        if self.colon:
            # "~:[ALTERNATIVE~;CONSEQUENT~] selects the ALTERNATIVE control
            # string if arg is false, and selects the CONSEQUENT control
            # string otherwise."
            apply_directives(stream, self.clauses[1 if args.next() else 0], args)
        elif self.atsign:
            # "~@[CONSEQUENT~] tests the argument.  If it is true, then
            # the argument is not used up by the ~[ command but remains
            # as the next one to be processed, and the one clause
            # CONSEQUENT is processed.  If the arg is false, then the
            # argument is used up, and the clause is not processed."
            if args.peek():
                apply_directives(stream, self.clauses[0], args)
            else:
                args.next()
        else:
            try:
                n = self.param(0, args)
                if n is None: n = args.next()
                apply_directives(stream, self.clauses[n], args)
            except IndexError:
                if self.separators[-1].colon:
                    # "If the last ~; used to separate clauses is ~:;
                    # instead, then the last clause is an 'else' clause
                    # that is performed if no other clause is selected."
                    apply_directives(stream, self.clauses[-1], args)

class EndIteration(Directive):
    modifiers_allowed = Modifiers.colon

class Iteration(DelimitedDirective):
    modifiers_allowed = Modifiers.all
    delimiter = EndIteration

    def append(self, x):
        if isinstance(x, Separator):
            raise FormatError("~~; not permitted in ~~{...~~}")
        super(Iteration, self).append(x)

    def delimited(self):
        self.body = prepare_directives(self.clauses[0]) if self.clauses[0] \
                                                        else None
        self.need_charpos = not self.body or \
            any([d.need_charpos for d in self.body if isinstance(d, Directive)])

    def format(self, stream, args):
        max = self.param(0, args, -1)
        body = self.body or prepare_directives(parse_control_string(args.next()))

        args = args if self.atsign else Arguments(args.next())
        next = (lambda args: Arguments(args.next(), args)) if self.colon \
                                                           else None
        write = stream.write
        i = 0
        while not args.empty or (i == 0 and self.delimiter.colon):
            if i == max: break
            i += 1
            try:
                iargs = next(args) if next else args
                fast_apply_directives(stream, write, body, iargs)
            except UpAndOut:
                continue
            except UpUpAndOut:
                break

class Recursive(Directive):
    modifiers_allowed = Modifiers.atsign
    need_charpos = True

    def format(self, stream, args):
        apply_directives(stream,
                         parse_control_string(args.next()),
                         args if self.atsign else Arguments(args.next()))

# Miscellaneous Operations

class EndCaseConversion(Directive):
    pass

class CaseConversion(DelimitedDirective):
    modifiers_allowed = Modifiers.all
    delimiter = EndCaseConversion

    def delimited(self):
        super(CaseConversion, self).delimited()
        self.body = self.clauses[0]

    def format(self, stream, args):
        if self.need_charpos:
            try:
                charpos = stream.charpos
            except AttributeError:
                charpos = 0
            s = CharposStream(StringIO(), charpos)
        else:
            s = StringIO()
        try:
            apply_directives(s, self.body, args)
            string = s.getvalue()
        finally:
            s.close()

        if self.colon and self.atsign:
            stream.write(string.upper())
        elif self.colon:
            stream.write(" ".join([s.capitalize() for s in string.split(" ")]))
        elif self.atsign:
            stream.write(string.capitalize())
        else:
            stream.write(string.lower())

class Plural(Directive):
    modifiers_allowed = Modifiers.all

    def __init__(self, *args):
        def prev(args): return args.peek(-1)
        def next(args): return args.next()
        def y(arg): return "y" if arg == 1 else "ies"
        def s(arg): return "" if arg == 1 else "s"

        super(Plural, self).__init__(*args)
        self.arg = prev if self.colon else next
        self.suffix = y if self.atsign else s

    def format(self, stream, args):
        stream.write(self.suffix(self.arg(args)))

# Miscellaneous Pseudo-Operations

class Separator(Directive):
    modifiers_allowed = Modifiers.colon

class Escape(Directive):
    modifiers_allowed = Modifiers.colon

    def __init__(self, *args):
        super(Escape, self).__init__(*args)

        if self.colon:
            iteration = self.governed_by(Iteration)
            if not (iteration and iteration.colon):
                raise FormatError("can't have ~~:^ outside of a "
                                  "~~:{...~~} construct")
        self.exception = UpUpAndOut if self.colon else UpAndOut

        if len(self.params) == 0:
            self.format = self.check_remaining_outer if self.colon \
                                                     else self.check_remaining
        elif len(self.params) in (1, 2, 3):
            self.format = self.check_params
        else:
            raise FormatError("too many parameters")

    def check_remaining(self, stream, args):
        if args.empty:
            raise UpAndOut()

    def check_remaining_outer(self, stream, args):
        if args.outer.empty:
            raise UpUpAndOut()

    def check_params(self, stream, args):
        # This could be split up, too.
        (param1, param2, param3) = (self.param(i, args) for i in range(3))
        if (param3 is not None and param1 <= param2 and param2 <= param3) or \
           (param2 is not None and param1 == param2) or \
           (param1 is not None and param1 == 0):
            raise self.exception()

format_directives = dict()
def register_directive(char, cls):
    assert len(char) == 1, "only single-character directives allowed"
    assert issubclass(cls, Directive), "invalid format directive class"

    format_directives[char.upper()] = format_directives[char.lower()] = cls

map(lambda x: register_directive(*x), {
    "%": Newline, "&": FreshLine, "|": Page, "~": Tilde,
    "R": Radix, "D": Decimal, "B": Binary, "O": Octal, "X": Hexadecimal,
    "A": Aesthetic, "S": Standard, "W": Write,
    "_": ConditionalNewline, "I": Indentation,
    "T": Tabulate, "<": Justification, ">": EndJustification,
    "*": GoTo, "[": Conditional, "]": EndConditional,
    "{": Iteration, "}": EndIteration, "?": Recursive,
    "(": CaseConversion, ")": EndCaseConversion, "P": Plural,
     ";": Separator, "^": Escape,
}.items())

def format_error(control, index, message, *args):
    offset = 2
    raise FormatError(format(None, "~?~%~V@T\"~A\"~%~V@T^",
                             message, args, offset, control, index + offset))

def parse_control_string(control, start=0, parent=None):
    assert isinstance(control, basestring), "control string must be a string"
    assert start >= 0, "can't start parsing from end"

    i = start
    end = len(control)
    while i < end:
        tilde = control.find("~", i)
        if tilde == -1:
            yield control[i:end]
            break
        elif tilde > i:
            yield control[i:tilde]
        i = tilde + 1

        params = []
        while i < end:
            # empty parameter
            if control[i] == ",":
                params.append(None)
                i += 1
                continue

            # numeric parameter
            mark = i
            if control[i] in "+-":
                i += 1
            while i < end and control[i].isdigit():
                i += 1
            if i > mark:
                params.append(int(control[mark:i]))
                if control[i] == ",":
                    i += 1
                continue

            # character parameter
            if control[i] == "'":
                params.append(control[i+1])
                i += 2
                if control[i] == ",":
                    i += 1
                continue

            # "variable" parameter
            if control[i] in "Vv":
                params.append(Directive.variable_parameter)
                i += 1
                if control[i] == ",":
                    i += 1
                continue

            # "remaining" parameter
            if control[i] == "#":
                params.append(Directive.remaining_parameter)
                i += 1
                if control[i] == ",":
                    i += 1
                continue
            break

        colon = atsign = False
        while i < end:
            if control[i] == ":":
                if colon: format_error(control, i, "too many colons")
                colon = True
                i += 1
            elif control[i] == "@":
                if atsign: format_error(control, i, "too many atsigns")
                atsign = True
                i += 1
            else:
                break

        char = control[i]
        i += 1
        try:
            d = format_directives[char](params, colon, atsign,
                                        control, tilde, i, parent)
        except FormatError, e:
            format_error(control, i, e.message)
        except KeyError:
            format_error(control, i, "unknown format directive")
        if isinstance(d, DelimitedDirective):
            for x in parse_control_string(control, i, d):
                try:
                    d.append(x)
                except FormatError, e:
                    if isinstance(x, Directive) and x is not d.delimiter:
                        i += x.start
                    format_error(control, i, e.message)
            i = d.end
        yield d
        if parent and d is parent.delimiter:
            return

class Formatter(object):
    def __init__(self, control):
        if isinstance(control, basestring):
            self.directives = tuple(parse_control_string(control))
        elif isinstance(control, (tuple, list)):
            self.directives = control
        self.need_charpos = any([d.need_charpos for d in self.directives \
                                     if isinstance(d, Directive)])

    def __call__(self, stream, *args):
        if not isinstance(stream, CharposStream) and self.need_charpos:
            stream = CharposStream(stream)
        if len(args) == 1 and isinstance(args[0], Arguments):
            args = args[0]
        else:
            args = Arguments(args)
        apply_directives(stream, self.directives, args)
        return args

def prepare_directives(directives):
    return [(d, True) if isinstance(d, basestring) else (d.format, False) \
                for d in directives]

def fast_apply_directives(stream, write, directives, args):
    """Apply a list of prepared directives."""
    for (x, string) in directives:
        if string:
            write(x)
        else:
            x(stream, args)

def apply_directives(stream, directives, args):
    for directive in directives:
        if isinstance(directive, basestring):
            stream.write(directive)
        else:
            directive.format(stream, args)

def format(destination, control, *args):
    if destination is None:
        stream = StringIO()
    elif destination is True:
        stream = sys.stdout
    else:
        stream = destination
    f = control if isinstance(control, Formatter) else Formatter(control)
    try:
        f(stream, *args)
    except UpAndOut:
        pass
    if destination is None:
        str = stream.getvalue()
        stream.close()
        return str
