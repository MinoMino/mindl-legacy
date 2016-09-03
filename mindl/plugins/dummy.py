# mindl - A plugin-based downloading tool.
# Copyright (C) 2016 Mino <mino@minomino.org>

# This file is part of mindl.

# mindl is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# mindl is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with mindl. If not, see <http://www.gnu.org/licenses/>.

import random
import hashlib

from time import sleep
from re import match
from mindl import BasePlugin

__version__ = "0.1"

class dummy(BasePlugin):
    name = "Dummy"
    options = ( ("n", 10),
                ("length", 1) )

    def __init__(self, url):
        self.count = 0

    @staticmethod
    def can_handle(url):
        if match("^dummy://.*$", url):
            return True

        return False

    def downloader(self):
        while self.count < int(self["n"]):
            sleep(int(self["length"]))
            self.count += 1
            data = hashlib.sha224(bytes([random.randint(0,255) for i in range(24)])).hexdigest()
            while random.randint(0, 9):
                data += hashlib.sha224(bytes([random.randint(0,255) for i in range(24)])).hexdigest()
            
            yield "{}.txt".format(self.count), data.encode()

