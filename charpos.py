import os
from array import array
from fcntl import ioctl
import termios
import printervars

class CharposStream(object):
    """An output stream wrapper that keeps track of character positions
    relative to the beginning of the current line."""

    def __init__(self, stream, charpos=0):
        self.stream = stream
        self.charpos = charpos
        self.closed = False

    def close(self):
        if not self.closed:
            self.closed = True

    def flush(self):
        assert not self.closed, "I/O operation on closed stream"
        self.stream.flush()

    def write(self, str):
        assert not self.closed, "I/O operation on closed stream"
        newline = str.rfind("\n")
        if newline == -1:
            self.charpos += len(str)
        else:
            self.charpos = len(str) - (newline + 1)
        self.stream.write(str)

    def terpri(self):
        assert not self.closed, "I/O operation on closed stream"
        self.stream.write("\n")
        self.charpos = 0

    def fresh_line(self):
        assert not self.closed, "I/O operation on closed stream"
        if self.charpos > 0:
            self.terpri()
            return True
        else:
            return False

    def getvalue(self):
        assert not self.closed, "I/O operation on closed stream"
        return self.stream.getvalue()

    @property
    def output_width(self):
        assert not self.closed, "I/O operation on closed stream"
        if printervars.print_right_margin:
            return printervars.print_right_margin
        if "COLUMNS" in os.environ:
            return int(os.environ["COLUMNS"])
        try:
            fd = self.stream.fileno()
            winsize = array("H", [0, 0, 0, 0])  # rows, columns, hsize, vsize
            ioctl(1, termios.TIOCGWINSZ, winsize)
            return winsize[1] or 80
        except:
            return 80
