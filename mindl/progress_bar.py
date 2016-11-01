import logging
import sys

from shutil import get_terminal_size

class StdoutStreamHandler(logging.StreamHandler):
    """
    The same as logging.StreamHandler(sys.stdout), but looks up sys.stdout before
    printing anything instead of saving it when instantiated. We use this for our
    custom progress bar.

    """
    def __init__(self):
        super().__init__(sys.stdout)
    
    def flush(self):
        self.stream = sys.stdout
        super().flush()

    def emit(self, record):
        self.stream = sys.stdout
        super().emit(record)

class LineReservePrinter:
    """
    Can be used with the 'with' keyword. It hooks stdout and "reserves" the last line
    to whatever it wants by doing some trickery with a carriage return.

    """
    def __init__(self, file):
        self.line = ""
        self._file = file
        self._save_stderr = None
        self._save_stdout = None

    def __enter__(self):
        self._save_stderr = sys.stderr
        self._save_stdout = sys.stdout
        sys.stdout = self
        sys.stderr = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._done()
        sys.stderr = self._save_stderr
        sys.stdout = self._save_stdout

    def write(self, data):
        if not data.rstrip("\n"):
            return
        
        f = self._file
        cols = get_terminal_size().columns
        # Clear the last line.
        f.write("\r" + " " * (cols-1))
        f.flush()
        # Return and write the data.
        out = "\r" + data
        if not out.endswith("\n"):
            out += "\n"
        f.write(out)
        
        # Write our string.
        f.write(self.line + "\r")
        f.flush()

    def flush(self):
        cols = get_terminal_size().columns
        self._file.write("\r" + " " * (cols-1) + "\r" + self.line + "\r")
        self._file.flush()

    def _done(self):
        f = self._file
        f.write("\r" + " " * (get_terminal_size().columns-1) + "\r")
        f.flush()

UNKNOWN_TOTAL = -1

class ProgressBar:
    def __init__(self, initial=0, total=UNKNOWN_TOTAL, empty="░", full="█", width=0, padding=2, units="", singular=""):
        if len(full) != 1:
            raise ValueError("'full' must be exactly one character long.")
        elif len(empty) != 1:
            raise ValueError("'empty' must be exactly one character long.")
        elif total < 1 and total != UNKNOWN_TOTAL:
            raise ValueError("'total' must be a positive number or exactly {}."
                .format(__name__ + ".UNKNOWN_TOTAL"))
        elif total != UNKNOWN_TOTAL and initial > total:
            raise ValueError("The initial value cannot be higher than the total.")
        
        self._current = max(0, initial)
        self._total = max(-1, total)
        self._empty = empty
        self._full = full
        self._width = max(0, int(width))
        self._padding = max(0, int(padding))
        self._units = units
        self._singular = singular

    def update(self, amount):
        if self._total == UNKNOWN_TOTAL:
            self._current = max(0, self._current + amount)
            return self._current
        else:
            self._current = max(0, min(self._total, self._current + amount))
            return self._current, self._total

    def get(self, msg=""):
        if self._units and self._singular and 0 < self._current <= 1:
            units = " " + self._singular
        elif self._units:
            units = " " + self._units
        else:
            units = ""

        # Also allow floats.
        if type(self._current) is float:
            current = "{:.2f}".format(self._current)
            total = "{:.2f}".format(self._total)
        else:
            current = "{:d}".format(self._current)
            total = "{:d}".format(self._total)
        
        if self._total == -1:
            out = "{}{} / ?{}".format(" " * self._padding, current, units)
        else:
            out = "{}{:3d}% {} ({}/{}){}".format(" " * self._padding, self._percentage(),
                self._bar(), current, total, units)
        if msg:
            out += " | " + msg

        return out

    def _percentage(self):
        return round(100 * self._current / self._total)

    def _bar(self):
        ratio = self._current / self._total
        if not self._width:
            width = round(get_terminal_size().columns / 4)
        else:
            width = self._width
        fulls = round(ratio * width)
        emptys = width - fulls
        return self._full * fulls + self._empty * emptys

