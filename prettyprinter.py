import sys
from collections import deque

__all__ = ["PrettyPrinter", "pprint"]

class Token(object):
    """Base class for prettyprinter tokens."""
    pass

class Newline(Token):
    def __init__(self, mandatory=False, fill=False, blankspace=0, offset=0):
        self.mandatory = mandatory
        self.fill = fill
        self.blankspace = blankspace
        self.offset = offset

class Begin(Token):
    """Begin a logical block.  If the offset is omitted or is None, use the
    length of the first string in the block."""

    def __init__(self, offset=None, prefix=None):
        self.offset = offset
        self.prefix = prefix

class End(Token):
    """End a logical block."""

    def __init__(self, suffix=None):
        self.suffix = suffix

class LogicalBlock(object):
    """A context manager for logical blocks."""

    def __init__(self, pp, lst, *args, **kwargs):
        if not isinstance(pp, PrettyPrinter):
            raise TypeError("not a pretty-printer")
        elif not (lst is None or isinstance(lst, (list, tuple))):
            raise TypeError("invalid logical block list")

        self.pp = pp
        self.list = lst
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
        if self.list is None or self.index == len(self.list):
            raise StopIteration
        value = self.list[self.index]
        self.index += 1
        return value

    def exit_if_list_exhausted(self):
        if self.list is None or self.index == len(self.list):
            raise StopIteration

class QueueEntry(object):
    def __init__(self, x, l): self.token = x; self.size = l
    def __len__(self): return self.size

class PrettyPrinter(object):
    infinity = 999999

    def __init__(self, width=80, file=sys.stdout):
        self.margin = int(width)
        if self.margin <= 0:
            raise ValueError("margin must be positive")
        if not file:
            raise RuntimeError("prettyprinting to nowhere")
        self.file = file
        self.space = self.margin
        self.scanstack = deque()
        self.printstack = deque()
        self.queue = deque()
        self.closed = False

    def write(self, str):
        self._scan(str)

    def newline(self, *args, **kwargs):
        self._scan(Newline(*args, **kwargs))

    def begin(self, *args, **kwargs):
        self._scan(Begin(*args, **kwargs))

    def end(self, *args, **kwargs):
        self._scan(End(*args, **kwargs))

    def logical_block(self, list=None, *args, **kwargs):
        return LogicalBlock(self, list, *args, **kwargs)

    def pprint(self, obj):
        from format import format

        if isinstance(obj, list):
            format(self, "~:<~@{~W~^, ~:_~}~:>", obj)
        elif isinstance(obj, tuple):
            format(self, "~<(~;~W,~^ ~:_~@{~W~^, ~:_~}~;)~:>", obj)
        elif isinstance(obj, (set, frozenset)):
            format(self, "~A~<([~;~@{~W~^, ~:_~}~;])~:>",
                   type(obj).__name__, list(obj))
        elif isinstance(obj, dict):
            format(self, "~<{~;~:@{~W: ~W~:^, ~:_~}~;}~:>", obj.items())
        elif hasattr(obj, "__pprint__"):
            obj.__pprint__(self)
        else:
            self.write(repr(obj))

    def close(self):
        if not self.closed:
            assert len(self.queue) == 0, "leftover items in output queue"
            assert len(self.scanstack) == 0, "leftover itmes on scan stack"
            assert len(self.printstack) == 0, "leftover items on print stack"
            self.closed = True

    def _scan(self, x):
        def push(x): self.scanstack.append(x)
        def pop(): return self.scanstack.pop()
        def top(): return self.scanstack[-1]
        def popbottom(): return self.scanstack.popleft()
        def empty(): return len(self.scanstack) == 0

        def enqueue(x, l):
            q = QueueEntry(x, l);
            self.queue.append(q);
            return q

        def flushqueue():
            """Output as many queue entries as possible."""
            while len(self.queue) > 0 and self.queue[0].size >= 0:
                q = self.queue.popleft()
                (x, l) = (q.token, q.size)
                self._output(x, l)
                self.leftotal += x.blankspace if isinstance(x, Newline) else l

        def reset():
            """Reset the size totals and ensure that the queue is empty."""
            self.leftotal = self.rightotal = 1
            assert len(self.queue) == 0, "queue should be empty"

        if isinstance(x, Begin):
            if empty(): reset()
            push(enqueue(x, -self.rightotal))
        elif isinstance(x, End):
            if empty(): self._output(x, 0)
            else:
                enqueue(x, 0)
                q = pop()
                q.size += self.rightotal
                if isinstance(q.token, Newline) and not empty():
                    q = pop()
                    q.size += self.rightotal
                if empty(): flushqueue()
        elif isinstance(x, Newline):
            if empty(): reset()
            else:
                q = top()
                if isinstance(q.token, Newline):
                    q.size += self.rightotal
                    pop()
            push(enqueue(x, -self.rightotal))
            self.rightotal += x.blankspace
        elif isinstance(x, basestring):
            if empty(): self._output(x, len(x))
            else:
                t = top().token
                if isinstance(t, Begin) and t.offset is None:
                    t.offset = len(x)

                enqueue(x, len(x))
                self.rightotal += len(x)
                while self.rightotal - self.leftotal > self.space:
                    popbottom().size = self.infinity
                    flushqueue()
        else:
            raise TypeError, "non-token"

    def _output(self, x, l):
        def push(x): self.printstack.append(x)
        def pop(): return self.printstack.pop()
        def top(): return self.printstack[-1]

        def indent(n, newline=False):
            if newline: self.file.write("\n")
            self.file.write(n * " ")

        if isinstance(x, Begin):
            if x.prefix: self._output(x.prefix, len(x.prefix))
            push((self.space - (x.offset or 0), l <= self.space))
        elif isinstance(x, End):
            if x.suffix: self._output(x.suffix, len(x.suffix))
            pop()
        elif isinstance(x, Newline):
            (block_offset, fits) = top()
            if x.mandatory:
                self.space = block_offset - x.offset
                indent(self.margin - self.space, True)
            elif fits:
                # Entire block fits; don't break line.
                self.space -= x.blankspace
                indent(x.blankspace)
            elif x.fill:
                # Fill- or block-style newline.
                if l > self.space:
                    self.space = block_offset - x.offset
                    indent(self.margin - self.space, True)
            else:
                # Linear-style newline.
                self.space = block_offset - x.offset
                indent(self.margin - self.space, True)
        elif isinstance(x, basestring):
            self.file.write(x)
            self.space -= l

def pprint(obj, *args, **kwargs):
    PrettyPrinter(*args, **kwargs).pprint(obj)
