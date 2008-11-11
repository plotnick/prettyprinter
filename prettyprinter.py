import sys
from collections import deque

class token(object):
    """Base class for prettyprinter tokens."""
    pass

class newline(token):
    def __init__(self, mandatory=False, fill=True, blankspace=0, offset=0):
        self.mandatory = mandatory
        self.fill = fill
        self.blankspace = blankspace
        self.offset = offset

class begin(token):
    """Begin a logical block.  If the offset is omitted or is None, use the
    length of the first string in the block."""
    def __init__(self, offset=None):
        self.offset = offset

class end(token):
    """End a logical block."""
    pass

class prettyprinter(object):
    infinity = 999999

    class queuentry(object):
        def __init__(self, x, l): self.token = x; self.size = l
        def __len__(self): return self.size

    def __init__(self, width=80, file=sys.stdout):
        self.margin = int(width); assert self.margin > 0, "negative margin"
        self.file = file; assert file, "prettyprinting to nowhere"
        self.space = self.margin
        self.scanstack = deque()
        self.printstack = deque()
        self.queue = deque()

    def __call__(self, toks):
        for x in toks: self.scan(x)
        assert len(self.queue) == 0, "leftover items in output queue"
        assert len(self.scanstack) == 0, "leftover itmes on scan stack"
        assert len(self.printstack) == 0, "leftover items on print stack"

    def scan(self, x):
        def push(x): self.scanstack.append(x)
        def pop(): return self.scanstack.pop()
        def top(): return self.scanstack[-1]
        def popbottom(): return self.scanstack.popleft()
        def empty(): return len(self.scanstack) == 0

        def enqueue(x, l):
            q = self.queuentry(x, l);
            self.queue.append(q);
            return q

        def flushqueue():
            """Output as many queue entries as possible."""
            while len(self.queue) > 0 and self.queue[0].size >= 0:
                q = self.queue.popleft()
                (x, l) = (q.token, q.size)
                self.output(x, l)
                self.leftotal += x.blankspace if isinstance(x, newline) else l

        def reset():
            """Reset the size totals and ensure that the queue is empty."""
            self.leftotal = self.rightotal = 1
            assert len(self.queue) == 0, "queue should be empty"

        if isinstance(x, begin):
            if empty(): reset()
            push(enqueue(x, -self.rightotal))
        elif isinstance(x, end):
            if empty(): self.output(x, 0)
            else:
                enqueue(x, 0)
                q = pop()
                q.size += self.rightotal
                if isinstance(q.token, newline) and not empty():
                    q = pop()
                    q.size += self.rightotal
                if empty(): flushqueue()
        elif isinstance(x, newline):
            if empty(): reset()
            else:
                q = top()
                if isinstance(q.token, newline):
                    q.size += self.rightotal
                    pop()
            push(enqueue(x, -self.rightotal))
            self.rightotal += x.blankspace
        elif isinstance(x, basestring):
            if empty(): self.output(x, len(x))
            else:
                t = top().token
                if isinstance(t, begin) and t.offset is None:
                    t.offset = len(x)

                enqueue(x, len(x))
                self.rightotal += len(x)
                while self.rightotal - self.leftotal > self.space:
                    popbottom().size = self.infinity
                    flushqueue()
        else:
            raise TypeError, "non-token"

    def output(self, x, l):
        def push(x): self.printstack.append(x)
        def pop(): return self.printstack.pop()
        def top(): return self.printstack[-1]

        def indent(n, newline=False):
            if newline: self.file.write("\n")
            self.file.write(n * " ")

        if isinstance(x, begin):
            push((self.space - (x.offset or 0), l <= self.space))
        elif isinstance(x, end): pop()
        elif isinstance(x, newline):
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

if __name__ == "__main__":
    print
    prettyprinter(40)([begin(offset=2),
                       "f(a, b, c, d)",
                       newline(fill=False), " + ", newline(),
                       "g(a, b, c, d)",
                       newline(fill=False), " + ", newline(),
                       "h(a, b, c, d)",
                       end()])
    print
