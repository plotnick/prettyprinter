from __future__ import with_statement

import sys
from collections import deque
from charpos import CharposStream
from bindings import bindings
import printervars

__all__ = ["PrettyPrinter", "pprint"]

class PrintLevelExceeded(StopIteration):
    pass

class Token(object):
    """Base class for prettyprinter tokens.

    Token instances should not be created directly by the user; the
    corresponding PrettyPrinter methods should be used instead."""

    size = 0

    def output(self, pp):
        """Send output to the given PrettyPrinter stream.

        These methods collectively correspond to Oppen's `print' routine."""
        pass

class Begin(Token):
    """Begin a logical block."""

    def __init__(self, prefix="", per_line=False):
        self.prefix = prefix
        self.per_line = per_line

    def output(self, pp):
        offset = pp.charpos
        if self.prefix:
            pp._write(self.prefix)
        if self.per_line:
            # Following XP, per-line prefixes are arranged to print directly
            # below the occurrence of the prefix on the first line.
            pp.prefix += (offset - len(pp.prefix)) * " " + self.prefix
        pp.printstack.append((pp.prefix,
                              pp.space,
                              pp.charpos - len(pp.prefix),
                              self.size <= pp.space))

class End(Token):
    """End a logical block."""

    def __init__(self, suffix=""):
        self.suffix = suffix

    def output(self, pp):
        if self.suffix:
            pp._write(self.suffix)
        try:
            pp.printstack.pop()
            pp.prefix = pp.printstack[-1][0] if pp.printstack else ""
        except IndexError:
            pass

class Newline(Token):
    """Base class for conditional newlines."""

    def __init__(self, blankspace=0):
        self.blankspace = blankspace

    def indent(self, pp, n):
        pp.terpri()
        pp._write(" " * n)

class Linear(Newline):
    def output(self, pp):
        (offset, fits) = pp.printstack[-1][-2:]
        if fits:
            pp._write(" " * self.blankspace)
        else:
            self.indent(pp, offset)

class Fill(Newline):
    def output(self, pp):
        (offset, fits) = pp.printstack[-1][-2:]
        if fits or self.size <= pp.space:
            pp._write(" " * self.blankspace)
        else:
            self.indent(pp, offset)

class Mandatory(Newline):
    def output(self, pp):
        self.indent(pp, pp.printstack[-1][-2])

class Indentation(Token):
    def __init__(self, offset=0, relative=False):
        self.offset = offset
        self.relative = relative

    def output(self, pp):
        (prefix, space, offset, fits) = pp.printstack.pop()
        offset = pp.margin - ((pp.space if self.relative else space) + \
                                  len(prefix) - self.offset)
        pp.printstack.append((prefix, space, offset, fits))

class String(Token):
    def __init__(self, string, size):
        self.string = string
        self.size = size

    def output(self, pp):
        pp._write(self.string)

class LogicalBlock(object):
    """A context manager for logical blocks."""

    def __init__(self, pp, lst, *args, **kwargs):
        self.pp = pp
        self.list = lst and list(lst)
        self.len = len(self.list) if lst else 0
        self.suffix = kwargs.pop("suffix", "")
        self.args = args
        self.kwargs = kwargs
        self.print_level_exceeded = None

    def __enter__(self):
        try:
            self.pp.begin(*self.args, **self.kwargs)
        except PrintLevelExceeded, e:
            self.pp.write("#")
            self.print_level_exceeded = e
            return iter([])
        self.index = 0
        return self

    def __exit__(self, type, value, traceback):
        if not self.print_level_exceeded:
            self.pp.end(suffix=self.suffix)
        return type and issubclass(type, StopIteration)

    def __iter__(self):
        return self

    def next(self):
        index = self.index
        if index == self.len:
            raise StopIteration
        elif index == printervars.print_length:
            self.pp.write("...")
            raise StopIteration
        value = self.list[index]
        self.index = index + 1
        return value

    def exit_if_list_exhausted(self):
        if self.index == self.len:
            raise StopIteration

class PrettyPrinter(CharposStream):
    def __init__(self, stream=sys.stdout, width=None, charpos=None):
        """Pretty-print to stream, with right margin at width characters,
        starting at position charpos."""
        if not stream:
            raise RuntimeError("pretty-printing to nowhere")
        self.stream = stream
        self.closed = False
        self.margin = self.output_width if width is None else int(width)
        if self.margin <= 0:
            raise ValueError("margin must be positive")
        if charpos is None:
            try:
                charpos = stream.charpos
            except AttributeError:
                charpos = 0

        self.space = self.margin - charpos
        self.scanstack = deque()
        self.printstack = list()
        self.prefix = ""
        self.queue = list()
        self.level = 0

    def write(self, string):
        """Enqueue a string for output."""
        assert not self.closed, "I/O operation on closed stream"
        l = len(string)
        stack = self.scanstack
        if not stack:
            self._write(string)
        else:
            q = self.queue[-1]
            if isinstance(q, String):
                # Don't create a seperate token; merge with the last one.
                q.string += string
                q.size += l
            else:
                tok = String(string, l)
                self.queue.append(tok)
            self.rightotal += l
            while self.rightotal - self.leftotal > self.space:
                stack.popleft().size = 999999   # infinity
                self.flush()

    def begin(self, *args, **kwargs):
        """Begin a new logical block."""
        assert not self.closed, "I/O operation on closed stream"
        if printervars.print_level is not None and \
                self.level >= printervars.print_level:
            raise PrintLevelExceeded(self.level)

        stack = self.scanstack
        if not stack:
            self.leftotal = self.rightotal = 1
            assert not self.queue, "queue should be empty"
        tok = Begin(*args, **kwargs)
        tok.size = -self.rightotal
        self.queue.append(tok)
        self.rightotal += len(tok.prefix)
        stack.append(tok)
        self.level += 1

    def end(self, *args, **kwargs):
        """End the current logical block."""
        assert not self.closed, "I/O operation on closed stream"
        tok = End(*args, **kwargs)
        stack = self.scanstack
        if not stack:
            tok.output(self)
        else:
            self.level -= 1
            self.queue.append(tok)
            self.rightotal += len(tok.suffix)

            top = stack.pop()
            top.size += self.rightotal
            if isinstance(top, Newline) and stack:
                top = stack.pop()
                top.size += self.rightotal
            if not stack:
                self.flush()

    def newline(self, fill=False, mandatory=False, blankspace=0):
        """Enqueue a conditional newline."""
        assert not self.closed, "I/O operation on closed stream"
        stack = self.scanstack
        if not stack:
            self.leftotal = self.rightotal = 1
            assert not self.queue, "queue should be empty"
        else:
            top = stack[-1]
            if isinstance(top, Newline):
                top.size += self.rightotal
                stack.pop()
        tok = Mandatory(blankspace) if mandatory \
                          else Fill(blankspace) if fill \
                          else Linear(blankspace)
        tok.size = -self.rightotal
        self.queue.append(tok)
        stack.append(tok)
        if blankspace:
            self.rightotal += blankspace

    def indent(self, *args, **kwargs):
        """Set the indentation level for the current logical block."""
        assert not self.closed, "I/O operation on closed stream"
        self.queue.append(Indentation(*args, **kwargs))

    def logical_block(self, lst=None, *args, **kwargs):
        """Return a context manager for a new logical block."""
        assert not self.closed, "I/O operation on closed stream"
        return LogicalBlock(self, lst, *args, **kwargs)

    def pprint(self, obj):
        """Pretty-print the given object."""
        def inflection(obj):
            if isinstance(obj, list):
                return ("[", "]")
            else:
                return ("%s([" % type(obj).__name__, "])")

        assert not self.closed, "I/O operation on closed stream"
        if isinstance(obj, basestring):
            self.write(repr(obj) if printervars.print_escape and \
                                     obj not in ("\n", "\t") \
                                 else obj)
        elif isinstance(obj, (int, float, long, complex)):
            self.write(repr(obj) if printervars.print_escape else str(obj))
        elif isinstance(obj, (list, set, frozenset, deque)):
            (prefix, suffix) = inflection(obj)
            with self.logical_block(obj, prefix=prefix, suffix=suffix) as l:
                for x in l:
                    self.pprint(x)
                    l.exit_if_list_exhausted()
                    self.write(", ")
                    if printervars.print_pretty:
                        self.newline(fill=True)
        elif isinstance(obj, tuple):
            with self.logical_block(obj, prefix="(", suffix=")") as l:
                x = l.next()
                self.pprint(x)
                self.write(",")
                l.exit_if_list_exhausted()
                self.write(" ")
                if printervars.print_pretty:
                    self.newline(fill=True)
                for x in l:
                    self.pprint(x)
                    l.exit_if_list_exhausted()
                    self.write(", ")
                    if printervars.print_pretty:
                        self.newline(fill=True)
        elif isinstance(obj, dict):
            with self.logical_block(obj.iteritems(),
                                    prefix="{", suffix="}") as l:
                for (key, value) in l:
                    self.pprint(key)
                    self.write(": ")
                    self.pprint(value)
                    l.exit_if_list_exhausted()
                    self.write(", ")
                    if printervars.print_pretty:
                        self.newline(fill=True)
        elif printervars.print_pretty and hasattr(obj, "__pprint__"):
            obj.__pprint__(self)
        else:
            self.write(repr(obj) if printervars.print_escape else str(obj))

    def flush(self):
        """Output as many queue entries as possible."""
        assert not self.closed, "I/O operation on closed stream"
        queue = self.queue
        i = 0
        total = 0
        for q in queue:
            if q.size < 0:
                break
            q.output(self)
            total += q.size
            i += 1
        if i > 0:
            self.queue = queue[i:]
            self.leftotal += total

    def close(self):
        if not self.closed:
            self.flush()
            assert not self.queue, "leftover items in output queue"
            assert not self.scanstack, "leftover itmes on scan stack"
            assert not self.printstack, "leftover items on print stack"
            self.closed = True

    def terpri(self):
        assert not self.closed, "I/O operation on closed stream"
        self.stream.write("\n" + self.prefix)
        self.space = self.margin - len(self.prefix)

    @property
    def charpos(self):
        return self.margin - self.space

    def _write(self, str):
        (before, newline, after) = str.partition("\n")
        self.stream.write(before)
        if newline:
            self.terpri()
            self._write(after)
        else:
            self.space -= len(before)

def pprint(obj, *args, **kwargs):
    pp = PrettyPrinter(*args, **kwargs)
    with bindings(printervars, print_pretty=True):
        pp.pprint(obj)
    pp.terpri()
    pp.close()
