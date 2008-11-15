from __future__ import with_statement

import sys
import re
from cStringIO import StringIO
from prettyprinter import PrettyPrinter

__all__ = ["format"]

class FormatError(StandardError):
    pass

class UpAndOut(Exception):
    pass

class Arguments(object):
    def __init__(self, args, outer=None):
        self.args = [arg for arg in args]
        self.cur = 0
        self.outer = outer

    def __len__(self): return len(self.args)
    def __getitem__(self, key): return self.args[key]
    def __iter__(self): return self
    def next(self):
        if self.cur == len(self.args):
            raise StopIteration
        arg = self.args[self.cur]; self.cur += 1
        return arg
    def peek(self): return self.args[self.cur]
    def prev(self): self.cur -= 1; arg = self.args[self.cur]; return arg
    def goto(self, n): self.cur = n
    def remaining(self): return len(self.args) - self.cur

class Directive(object):
    prefix_param = re.compile(r"(?:([+-]?\d+)|'(.)|([Vv])|(#)),?")
    variable_parameter = object()
    remaining_parameter = object()
    colon_allowed = atsign_allowed = False

    def __init__(self, params, colon, atsign, control, start, end):
        if colon and not self.colon_allowed and \
                atsign and not self.atsign_allowed:
            raise FormatError("neither colon nor atsign allowed "
                              "for this directive")
        elif colon and not self.colon_allowed:
            raise FormatError("colon not allowed for this directive")
        elif atsign and not self.atsign_allowed:
            raise FormatError("atsign not allowed for this directive")

        self.params = params; self.colon = colon; self.atsign = atsign
        self.control = control; self.start = start; self.end = end

    def __str__(self): return self.control[self.start:self.end]
    def __len__(self): return self.end - self.start

    def param(self, n, args, default=None):
        if n < len(self.params):
            p = self.params[n]
            if p is Directive.variable_parameter: p = args.next()
            elif p is Directive.remaining_parameter: p = args.remaining()
            return p if p is not None else default
        else:
            return default

class Literal(Directive):
    """Strictly speaking, string literals are not directives, but treating
    them as if they were simplifies the logic."""

    def __init__(self, control, start, end):
        super(Literal, self).__init__(None, False, False, control, start, end)
        assert end > start

    def format(self, stream, args):
        stream.write(str(self))

class Newline(Directive):
    def format(self, stream, args):
        stream.write("\n" * self.param(0, args, 1))

class FreshLine(Directive):
    def format(self, stream, args):
        stream.write("~" * self.param(0, args, 1))

class Tilde(Directive):
    def format(self, stream, args):
        stream.write("~" * self.param(0, args, 1))

class Aesthetic(Directive):
    colon_allowed = atsign_allowed = True

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

class Representation(Directive):
    colon_allowed = atsign_allowed = True

    def format(self, stream, args):
        stream.write(repr(args.next()))

class Write(Directive):
    colon_allowed = atsign_allowed = True

    def format(self, stream, args):
        arg = args.next()
        if isinstance(stream, PrettyPrinter):
            stream.pprint(arg)
        else:
            stream.write(repr(arg))

class Numeric(Directive):
    """Base class for decimal, binary, octal, and hex conversion directives."""

    colon_allowed = atsign_allowed = True

    def format(self, stream, args):
        def abs(n):
            return n if n > 0 else -n

        def commafy(s, commachar, comma_interval):
            """Add commachars between groups of comma_interval digits."""
            first = len(s) % comma_interval
            a = [s[0:first]] if first > 0 else []
            for i in range(first, len(s), comma_interval):
                a.append(s[i:i + comma_interval])
            return commachar.join(a)

        mincol = int(self.param(0, args, 0))
        padchar = str(self.param(1, args, " "))
        commachar = str(self.param(2, args, ","))
        comma_interval = int(self.param(3, args, 3))

        n = args.next()
        s = self.convert(abs(n))
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

class Decimal(Numeric):
    def convert(self, n):
        return "%d" % n

class Binary(Numeric):
    octal_digits = ("000", "001", "010", "011", "100", "101", "110", "111")

    def convert(self, n):
        return "".join(self.octal_digits[int(digit)] \
                           for digit in "%o" % n).lstrip("0")

class Octal(Numeric):
    def convert(self, n):
        return "%o" % n

class Hexadecimal(Numeric):
    def convert(self, n):
        return "%x" % n

class Plural(Directive):
    colon_allowed = atsign_allowed = True

    def format(self, stream, args):
        if self.colon: args.prev()
        stream.write(("y" if args.next() == 1 else "ies") if self.atsign else \
                     ("" if args.next() == 1 else "s"))

class Separator(Directive):
    colon_allowed = True

class Escape(Directive):
    colon_allowed = True

    def format(self, stream, args):
        if self.colon and not args.outer:
            raise FormatError("attempt to use ~:^ outside a ~:{...~} construct")

        (param1, param2, param3) = (self.param(i, args) for i in range(3))
        if (param3 is not None and param1 <= param2 and param2 <= param3) or \
           (param2 is not None and param1 == param2) or \
           (param1 is not None and param1 == 0) or \
           ((args.outer if self.colon else args).remaining() == 0):
            raise UpAndOut(self)

class Goto(Directive):
    colon_allowed = atsign_allowed = True

    def format(self, stream, args):
        if self.atsign:
            n = self.param(0, args, 0)
            if n >= 0 and n < len(args): args.goto(n)
            else: raise FormatError("Index %d is out of bounds." % n)
        else:
            for i in range(self.param(0, args, 1)):
                if self.colon: args.prev()
                else: args.next()

class DelimitedDirective(Directive):
    """Delimited directives, such as conditional expressions and
    justifications, are composed of an opening delimiter, zero or more
    clauses separated by a separator, and a closing delimiter.

    Subclasses should define a class attribute, delimiter, that specifies
    the class of the closing delimiter.  Instances will have that attribute
    set to the instance of that class actually encountered."""

    def __init__(self, params, colon, atsign, control, start, end):
        super(DelimitedDirective, self).__init__(params, colon, atsign,
                                                 control, start, end)
        self.clauses = [[]]
        self.separators = []

    def __getitem__(self, key): return self.clauses[key]

    def append(self, x):
        if isinstance(x, Separator):
            self.separators.append(x)
            self.clauses.append([])
        elif isinstance(x, self.delimiter):
            self.delimiter = x
        else:
            self.clauses[len(self.separators)].append(x)
        self.end = x.end

class ConditionalNewline(Directive):
    colon_allowed = atsign_allowed = True

    def format(self, stream, args):
        stream.newline(mandatory=(self.colon and self.atsign), fill=self.colon)

class EndJustification(Directive):
    colon_allowed = True

class Justification(DelimitedDirective):
    """This class actually implements two essentially unrelated format
    directives: justification (~<...~>) and pprint-logical-block (~<...~:>).
    Blame Dick Waters."""

    colon_allowed = atsign_allowed = True
    delimiter = EndJustification

    def format(self, stream, args):
        if self.delimiter.colon:
            # pprint-logical-block
            if not isinstance(stream, PrettyPrinter):
                stream = PrettyPrinter(file=stream)

            # Note: with the colon modifier, the prefix & suffix default to
            # square, not round brackets; this is Python, not Lisp.
            prefix = "[" if self.colon else ""
            suffix = "]" if self.colon else ""
            if len(self.clauses) == 0:
                body = []
            elif len(self.clauses) == 1:
                (body,) = self.clauses
            elif len(self.clauses) == 2:
                ((prefix,), body) = self.clauses
            elif len(self.clauses) == 3:
                ((prefix,), body, (suffix,)) = self.clauses
            else:
                raise FormatError("too many segments for ~<...~:>")

            list = [x for x in args] if self.atsign else args.next()
            with stream.logical_block(list, offset=0,
                                      prefix=str(prefix),
                                      suffix=str(suffix)) as l:
                try:
                    apply_directives(body, stream, Arguments(l))
                except UpAndOut:
                    pass
        else:
            raise FormatError("justification not yet implemented")

class EndConditional(Directive):
    pass

class Conditional(DelimitedDirective):
    colon_allowed = atsign_allowed = True
    delimiter = EndConditional

    def format(self, stream, args):
        if self.colon:
            # "~:[ALTERNATIVE~;CONSEQUENT~] selects the ALTERNATIVE control
            # string if arg is false, and selects the CONSEQUENT control
            # string otherwise."
            if len(self.clauses) != 2:
                raise FormatError("must specify exactly two sections")
            apply_directives(self.clauses[1 if args.next() else 0], stream, args)
        elif self.atsign:
            # "~@[CONSEQUENT~] tests the argument.  If it is true, then
            # the argument is not used up by the ~[ command but remains
            # as the next one to be processed, and the one clause
            # CONSEQUENT is processed.  If the arg is false, then the
            # argument is used up, and the clause is not processed."
            if len(self.clauses) != 1:
                raise FormatError("can only specify one section")
            if args.peek():
                apply_directives(self.clauses[0], stream, args)
            else:
                args.next()
        else:
            try:
                n = self.param(0, args)
                if n is None: n = args.next()
                apply_directives(self.clauses[n], stream, args)
            except IndexError:
                if self.separators[-1].colon:
                    # "If the last ~; used to separate clauses is ~:;
                    # instead, then the last clause is an 'else' clause
                    # that is performed if no other clause is selected."
                    apply_directives(self.clauses[-1], stream, args)

class EndIteration(Directive):
    colon_allowed = True

class Iteration(DelimitedDirective):
    colon_allowed = atsign_allowed = True
    delimiter = EndIteration

    def format(self, stream, args):
        max = self.param(0, args, -1)
        body = self.clauses[0] or [x for x in parse_control_string(args.next())]

        outer = args if self.atsign else Arguments(args.next())
        inner = (lambda outer: Arguments(outer.next(), outer)) if self.colon \
            else lambda outer: outer

        i = 0
        while outer.remaining() > 0 or (i == 0 and self.delimiter.colon):
            if i == max: break
            i += 1
            try:
                apply_directives(body, stream, inner(outer))
            except UpAndOut, e:
                if e.args[0].colon: break
                else: continue

class Recursive(Directive):
    atsign_allowed = True

    def format(self, stream, args):
        apply_directives(parse_control_string(args.next()),
                         stream,
                         args if self.atsign else Arguments(args.next()))

directives = {
    "%": Newline, "&": FreshLine, "~": Tilde,
    "A": Aesthetic, "R": Representation, "S": Representation, "W": Write,
    "D": Decimal, "B": Binary, "O": Octal, "X": Hexadecimal,
    "*": Goto,
    "_": ConditionalNewline,
    "<": Justification, ">": EndJustification,
    "[": Conditional, "]": EndConditional,
    "{": Iteration, "}": EndIteration,
    "?": Recursive,
    "P": Plural,
     ";": Separator, "^": Escape,
}

def parse_control_string(control, start=0, delimiter=None):
    assert isinstance(control, basestring), "control string must be a string"
    assert start >= 0, "can't start parsing from end"

    while start < len(control):
        tilde = control.find("~", start)
        if tilde == -1:
            yield Literal(control, start, len(control))
            break
        elif tilde > start:
            yield Literal(control, start, tilde)
        i = tilde + 1

        params = []
        while True:
            # Match optional parameters, separated by commas.
            m = Directive.prefix_param.match(control, i)
            if m:
                if m.group(1): params.append(int(m.group(1)))
                elif m.group(2): params.append(m.group(2))
                elif m.group(3): params.append(Directive.variable_parameter)
                elif m.group(4): params.append(Directive.remaining_parameter)
                i = m.end()
            elif control[i] == ",": params.append(None); i += 1
            else: break

        colon = atsign = False
        while True:
            if control[i] == ":":
                if colon: raise FormatError("too many colons")
                colon = True; i += 1
            elif control[i] == "@":
                if atsign: raise FormatError("too many atsigns")
                atsign = True; i += 1
            elif control[i].upper() in directives.keys():
                d = directives[control[i].upper()](params, colon, atsign,
                                                   control, tilde, i+1); i += 1
                if isinstance(d, DelimitedDirective):
                    for x in parse_control_string(control, i, d.delimiter):
                        d.append(x)
                    i = d.end
                yield d
                if delimiter and isinstance(d, delimiter): return
                else: break
            else:
                raise FormatError("unknown format directive " + \
                                      control[tilde:i+1].upper())
        start = i

def apply_directives(directives, stream, args):
    for d in directives:
        d.format(stream, args)

def format(destination, control, *args):
    if destination is None:
        stream = StringIO()
    elif destination is True:
        stream = sys.stdout
    else:
        stream = destination
    try:
        apply_directives(parse_control_string(control), stream, Arguments(args))
    except UpAndOut:
        pass
    if destination is None:
        str = stream.getvalue()
        stream.close()
        return str
