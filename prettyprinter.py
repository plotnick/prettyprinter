import sys
from collections import deque

class token(object):
    """Base class for prettyprinter tokens."""
    pass

class string(token):
    def __init__(self, s):
        self.string = s
    def __len__(self):
        return len(self.string)

class linebreak(token):
    def __init__(self, offset=0, blankspace=1):
        self.offset = offset
        self.blankspace = blankspace

class discretionary(linebreak):
    def __init__(self):
        super(self, discretionary).__init__(blankspace=0)

class newline(linebreak):
    def __init__(self):
        super(self, discretionary).__init__(blankspace=9999)

class begin(token):
    consistent, inconsistent = range(2)

    def __init__(self, offset=2, breaktype=inconsistent):
        self.offset = offset
        self.breaktype = breaktype

class end(token):
    pass

class prettyprinter(object):
    def __init__(self, width=80, file=sys.stdout):
        self.space = self.margin = int(width); assert self.margin > 0
        self.file = file; assert file
        self.scanstack = deque()
        self.printstack = deque()
        self.arraysize = 3*self.margin
        self.stream = [None for i in range(0, self.arraysize)]
        self.size = [None for i in range(0, self.arraysize)]

    def __call__(self, toks):
        for x in toks: self.scan(x)

    def scan(self, x):
        assert isinstance(x, token), "non-token instance"
        if isinstance(x, begin):
            if len(self.scanstack) == 0:
                self.leftotal = self.rightotal = 1
                self.left = self.right = 0
            else:
                self.advanceright()
            self.stream[self.right] = x
            self.size[self.right] = -self.rightotal
            self.scanstack.append(self.right)
        elif isinstance(x, end):
            if len(self.scanstack) == 0:
                self.pprint(x, 0)
            else:
                self.advanceright()
                self.stream[self.right] = x
                self.size[self.right] = 0
                y = self.scanstack.pop()
                self.size[y] += self.rightotal
                if isinstance(self.stream[y], linebreak) and len(self.scanstack):
                    z = self.scanstack.pop()
                    self.size[z] += self.rightotal
                if len(self.scanstack) == 0:
                    self.advanceleft(self.stream[self.left], self.size[self.left])
        elif isinstance(x, linebreak):
            if len(self.scanstack) == 0:
                self.rightotal = 1
                self.left = self.right = 0
            else:
                self.advanceright()
                y = self.scanstack[-1]
                if isinstance(self.stream[y], linebreak):
                    self.scanstack.pop()
                    self.size[y] += self.rightotal
            self.stream[self.right] = x
            self.size[self.right] = -self.rightotal
            self.scanstack.append(self.right)
            self.rightotal += x.blankspace
        elif isinstance(x, string):
            if len(self.scanstack) == 0:
                self.pprint(x, len(x))
            else:
                self.advanceright()
                self.stream[self.right] = x
                self.size[self.right] = len(x)
                self.rightotal += len(x)
                while self.rightotal - self.leftotal > self.space:
                    self.size[self.scanstack.popleft()] = 999999
                    self.advanceleft(self.stream[self.left], self.size[self.left])

    def advanceright(self):
        self.right = (self.right + 1) % self.arraysize
        assert self.left < self.right

    def advanceleft(self, x, l):
        if l >= 0:
            self.pprint(x, l)
            self.leftotal += x.blankspace if isinstance(x, linebreak) else l
            if self.left < self.right:
                self.left = (self.left + 1) % self.arraysize
                self.advanceleft(self.stream[self.left], self.size[self.left])

    def pprint(self, x, l):
        def indent(x): self.file.write("\n" + x*" ")

        if isinstance(x, begin):
            self.printstack.append(self.space - x.offset if l > self.space else 0)
        elif isinstance(x, end):
            self.printstack.pop()
        elif isinstance(x, linebreak):
            # So far, inconsistent breaks assumed.
            if l > self.space:
                self.space = self.printstack[-1] - x.offset
                indent(self.margin - self.space)
            else:
                self.file.write(x.blankspace*" ")
                self.space -= x.blankspace
        elif isinstance(x, string):
            self.file.write(x.string)
            self.space -= l

if __name__ == "__main__":
    prettyprinter(15)([begin(),
                       begin(), string("f(a, b, c, d)"), end(),
                       linebreak(offset=2), string("+"), linebreak(offset=2),
                       begin(), string("g(a, b, c, d)"), end(),
                       end()])
    print
