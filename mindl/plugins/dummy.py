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
import os

from time import sleep
from re import match
from mindl import BasePlugin, download_directory

__version__ = "0.1"

class dummy(BasePlugin):
    """Simulates downloads by creating random data and sleeping in between files. Useful for testing stuff."""
    name = "Dummy"
    options = ( ("n", 20),
                ("length", 0.75),
                ("cleanup", 1),
                ("progress", 1) )

    def __init__(self, url):
        self.count = 0

    def progress(self):
        if bool(int(self["progress"])):
            return self.count, int(self["n"])

    @staticmethod
    def can_handle(url):
        if match("^dummy://.*$", url):
            return True

        return False

    def downloader(self):
        while self.count < int(self["n"]):
            sleep(float(self["length"]))
            self.count += 1
            data = hashlib.sha224(bytes([random.randint(0,255) for i in range(24)])).hexdigest()
            while random.randint(0, 9):
                data += hashlib.sha224(bytes([random.randint(0,255) for i in range(24)])).hexdigest()
            
            if not self.count % 5:
                self.logger.debug("順調に進んでるぞ～")
            if not self.count % 13:
                self.logger.error("大変！エラーが発生したよ！\nなんとかしてくれよ～")
            
            yield "{}.txt".format(self.count), data.encode()

    def finalize(self):
        if bool(int(self["cleanup"])):
            from shutil import rmtree
            self.logger.info("Cleaning up dummy files...")
            rmtree(os.path.join(download_directory(), self.directory()))
