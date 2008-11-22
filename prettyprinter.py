from __future__ import with_statement

import sys
from collections import deque

__all__ = ["PrettyPrinter", "pprint"]

class Token(object):
    """Base class for prettyprinter tokens."""
    size = 0

class Begin(Token):
    """Begin a logical block."""

    def __init__(self, prefix="", per_line=False):
        self.prefix = prefix
        self.per_line = per_line

    def output(self, pp):
        if self.prefix:
            pp._write(self.prefix)
        pp.printstack.append(((self.prefix, self.per_line), pp.space,
                              pp.charpos, self.size <= pp.space))

class End(Token):
    """End a logical block."""

    def __init__(self, suffix=""):
        self.suffix = suffix

    def output(self, pp):
        if self.suffix:
            pp._write(self.suffix)
        try:
            pp.printstack.pop()
        except IndexError:
            pass

class Newline(Token):
    def indent(self, pp, n):
        pp.terpri()
        pp._write(" " * n)

class Linear(Newline):
    def output(self, pp):
        (offset, fits) = pp.printstack[-1][-2:]
        if not fits:
            self.indent(pp, offset)

class Fill(Newline):
    def output(self, pp):
        (offset, fits) = pp.printstack[-1][-2:]
        if not fits and self.size > pp.space:
            self.indent(pp, offset)

class Mandatory(Newline):
    def output(self, pp):
        self.indent(pp, pp.printstack[-1][-2])

class Indentation(Token):
    def __init__(self, offset=0, relative=False):
        self.offset = offset
        self.relative = relative

    def output(self, pp):
        ((prefix, per_line), block, offset, fits) = pp.printstack.pop()
        offset = pp.margin - ((pp.space if self.relative else block) + \
                                  (len(prefix) if per_line else 0) - \
                                  self.offset)
        pp.printstack.append(((prefix, per_line), block, offset, fits))

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
        self.list = lst
        self.len = len(lst) if lst else 0
        self.suffix = kwargs.pop("suffix", "")
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        self.pp.begin(*self.args, **self.kwargs)
        self.index = 0
        return self

    def __exit__(self, type, value, traceback):
        self.pp.end(suffix=self.suffix)
        if type is StopIteration:
            return True

    def __iter__(self):
        return self

    def next(self):
        index = self.index
        if index == self.len:
            raise StopIteration
        value = self.list[index]
        self.index = index + 1
        return value

    def exit_if_list_exhausted(self):
        if self.index == self.len:
            raise StopIteration

class PrettyPrinter(object):
    def __init__(self, width=80, stream=sys.stdout, charpos=None):
        self.margin = int(width)
        if self.margin <= 0:
            raise ValueError("margin must be positive")
        if not stream:
            raise RuntimeError("prettyprinting to nowhere")
        self.stream = stream
        if charpos is None:
            try:
                charpos = stream.charpos
            except AttributeError:
                charpos = 0
        self.space = self.margin - charpos
        self.scanstack = deque()
        self.printstack = list()
        self.queue = list()
        self.prefix = ""
        self.closed = False

    def write(self, obj):
        if isinstance(obj, basestring):
            self.string(obj)
        elif isinstance(obj, (int, float, long, complex)):
            self.string(str(obj))
        elif isinstance(obj, list):
            with self.logical_block(obj, prefix="[", suffix="]") as l:
                for x in l:
                    self.write(x)
                    l.exit_if_list_exhausted()
                    self.write(", ")
                    self.newline(fill=True)
        elif isinstance(obj, tuple):
            with self.logical_block(obj, prefix="(", suffix=")") as l:
                self.write(l.next())
                self.write(",")
                l.exit_if_list_exhausted()
                self.write(" ")
                self.newline(fill=True)
                for x in l:
                    self.write(x)
                    l.exit_if_list_exhausted()
                    self.write(", ")
                    self.newline(fill=True)
        elif isinstance(obj, (set, frozenset, deque)):
            with self.logical_block(tuple(obj),
                                    prefix="%s(" % type(obj).__name__,
                                    suffix=")") as l:
                for x in l:
                    self.write(x)
                    l.exit_if_list_exhausted()
                    self.write(", ")
                    self.newline(fill=True)
        elif isinstance(obj, dict):
            with self.logical_block(obj.items(), prefix="{", suffix="}") as l:
                for key, value in l:
                    self.write(key)
                    self.write(": ")
                    self.write(value)
                    l.exit_if_list_exhausted()
                    self.write(", ")
                    self.newline(fill=True)
        elif hasattr(obj, "__pprint__"):
            obj.__pprint__(self)
        else:
            self.string(str(obj))

    def begin(self, *args, **kwargs):
        stack = self.scanstack
        if not stack:
            self.leftotal = self.rightotal = 1
            assert not self.queue, "queue should be empty"
        tok = Begin(*args, **kwargs)
        tok.size = -self.rightotal
        self.prefix = tok.prefix if tok.per_line else ""
        self.queue.append(tok)
        self.rightotal += len(tok.prefix)
        stack.append(tok)

    def end(self, *args, **kwargs):
        tok = End(*args, **kwargs)
        stack = self.scanstack
        if not stack:
            tok.output(self)
        else:
            self.queue.append(tok)
            self.rightotal += len(tok.suffix)

            top = stack.pop()
            top.size += self.rightotal
            if isinstance(top, Newline) and stack:
                top = stack.pop()
                top.size += self.rightotal
            if not stack:
                self.flush()

    def newline(self, fill=False, mandatory=False):
        stack = self.scanstack
        if not stack:
            self.leftotal = self.rightotal = 1
            assert not self.queue, "queue should be empty"
        else:
            top = stack[-1]
            if isinstance(top, Newline):
                top.size += self.rightotal
                stack.pop()
        tok = Mandatory() if mandatory \
                          else Fill() if fill \
                          else Linear()
        tok.size = -self.rightotal
        self.queue.append(tok)
        stack.append(tok)

    def string(self, s):
        l = len(s)
        stack = self.scanstack
        if not stack:
            self._write(s)
        else:
            q = self.queue[-1]
            if isinstance(q, String):
                # Don't create a seperate token; merge with the last one.
                q.string += s
                q.size += l
            else:
                tok = String(s, l)
                self.queue.append(tok)
            self.rightotal += l
            while self.rightotal - self.leftotal > self.space:
                stack.popleft().size = 999999   # infinity
                self.flush()

    def indent(self, *args, **kwargs):
        self.queue.append(Indentation(*args, **kwargs))

    def logical_block(self, lst=None, *args, **kwargs):
        return LogicalBlock(self, lst, *args, **kwargs)

    def flush(self):
        """Output as many queue entries as possible."""
        queue = self.queue
        i = 0
        n = len(queue)
        total = 0
        while i < n:
            q = queue[i]
            size = q.size
            if size < 0:
                break
            q.output(self)
            total += size
            i += 1
        if i > 0:
            self.queue = queue[i:]
            self.leftotal += total

    def close(self):
        if not self.closed:
            assert not self.queue, "leftover items in output queue"
            assert not self.scanstack, "leftover itmes on scan stack"
            assert not self.printstack, "leftover items on print stack"
            self.closed = True

    def _write(self, str):
        (before, newline, after) = str.partition("\n")
        self.stream.write(before)
        if newline:
            self.terpri()
            self._write(after)
        else:
            self.space -= len(before)

    def terpri(self):
        prefix = self.prefix
        self.stream.write("\n" + prefix)
        self.space = self.margin - (len(prefix) if prefix else 0)

    @property
    def charpos(self):
        return self.margin - self.space

def pprint(obj, *args, **kwargs):
    PrettyPrinter(*args, **kwargs).write(obj)
