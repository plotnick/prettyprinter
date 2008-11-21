from __future__ import with_statement
import sys
from collections import deque

__all__ = ["PrettyPrinter", "pprint"]

class Token(object):
    """Base class for prettyprinter tokens."""

class Begin(Token):
    """Begin a logical block."""

    def __init__(self, prefix=None):
        self.prefix = prefix

    def output(self, pp):
        if self.prefix:
            pp.stream.write(self.prefix)
        pp.printstack.append((pp.space, self.size <= pp.space))

class End(Token):
    """End a logical block."""

    def __init__(self, suffix=None):
        self.suffix = suffix
        self.size = 0

    def output(self, pp):
        if self.suffix:
            pp.stream.write(self.suffix)
        if pp.printstack:
            pp.printstack.pop()

class Newline(Token):
    pass

class Linear(Newline):
    def output(self, pp):
        (block_offset, fits) = pp.printstack[-1]
        if not fits:
            pp.space = block_offset
            pp.stream.write("\n" + " " * (pp.margin - pp.space))

class Fill(Newline):
    def output(self, pp):
        (block_offset, fits) = pp.printstack[-1]
        if not fits and self.size > pp.space:
            pp.space = block_offset
            pp.stream.write("\n" + " " * (pp.margin - pp.space))

class Mandatory(Newline):
    def output(self, pp):
        (block_offset, fits) = pp.printstack[-1]
        pp.space = block_offset
        pp.stream.write("\n" + " " * (pp.margin - pp.space))

class Indentation(Token):
    def __init__(self, n=0):
        self.offset = n
        self.size = 0

    def output(self, pp):
        (block_offset, fits) = pp.printstack.pop()
        pp.printstack.append((block_offset - self.offset, fits))

class String(Token):
    def __init__(self, string, size):
        self.string = string
        self.size = size

    def output(self, pp):
        pp.stream.write(self.string)
        pp.space -= self.size

class LogicalBlock(object):
    """A context manager for logical blocks."""

    def __init__(self, pp, lst, *args, **kwargs):
        assert isinstance(pp, PrettyPrinter), "not a pretty-printer"
        assert lst is None or isinstance(lst, (list, tuple)), \
            "invalid logical block list"

        self.pp = pp
        self.list = lst
        self.len = len(lst) if lst else 0
        self.suffix = kwargs.pop("suffix", None)
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
    def __init__(self, width=80, stream=sys.stdout):
        self.margin = int(width)
        if self.margin <= 0:
            raise ValueError("margin must be positive")
        if not stream:
            raise RuntimeError("prettyprinting to nowhere")
        self.stream = stream
        self.space = self.margin
        self.scanstack = deque()
        self.printstack = list()
        self.queue = list()
        self.closed = False

    def write(self, obj):
        from format import format

        if isinstance(obj, basestring):
            self.string(obj)
        elif isinstance(obj, (int, float, long, complex)):
            self.string(str(obj))
        elif isinstance(obj, list):
            format(self, "~:<~@{~W~^, ~:_~}~:>", obj)
        elif isinstance(obj, tuple):
            format(self, "~<(~;~W,~^ ~:_~@{~W~^, ~:_~}~;)~:>", obj)
        elif isinstance(obj, (set, frozenset, deque)):
            format(self, "~A~<([~;~@{~W~^, ~:_~}~;])~:>",
                   type(obj).__name__, list(obj))
        elif isinstance(obj, dict):
            format(self, "~<{~;~:@{~W: ~W~:^, ~:_~}~;}~:>", obj.items())
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
        self.queue.append(tok)
        stack.append(tok)

    def end(self, *args, **kwargs):
        tok = End(*args, **kwargs)
        stack = self.scanstack
        if not stack:
            tok.output(self)
        else:
            self.queue.append(tok)
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
            self.stream.write(s)
            self.space -= l
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

    def indent(self, n=0):
        self.queue.append(Indentation(n))

    def logical_block(self, list=None, *args, **kwargs):
        return LogicalBlock(self, list, *args, **kwargs)

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

def pprint(obj, *args, **kwargs):
    PrettyPrinter(*args, **kwargs).write(obj)
