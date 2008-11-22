class CharposStream(object):
    """An output stream wrapper that keeps track of character positions
    relative to the beginning of the current line."""

    def __init__(self, stream, charpos=0):
        self.stream = stream
        self.charpos = charpos
        self.closed = False

    def close(self):
        if not self.closed:
            self.stream.close()
            self.close = True

    def flush(self):
        self.stream.flush()

    def write(self, str):
        newline = str.rfind("\n")
        if newline == -1:
            self.charpos += len(str)
        else:
            self.charpos = len(str) - (newline + 1)
        self.stream.write(str)

    def terpri(self):
        self.stream.write("\n")
        self.charpos = 0

    def fresh_line(self):
        if self.charpos > 0:
            self.terpri()
            return True
        else:
            return False

    def getvalue(self):
        return self.stream.getvalue()
