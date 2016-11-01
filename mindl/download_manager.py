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

import logging
import os.path
import sys
import os

from .base_plugin import BasePlugin
from .progress_bar import LineReservePrinter, ProgressBar

class DownloadManager():
    base_directory = "downloads"
    
    def __init__(self, plugin):
        self.logger = logging.getLogger("mindl")
        self._plugin = plugin
        self._count = 0
        self._progress_bar = None

    def start_download(self):
        if not self._plugin.has_valid_options():
            self.logger.critical("A download started with invalid options!")
            sys.exit(1)

        self.logger.info("Starting download...")
        try:
            with LineReservePrinter(sys.stdout) as lrp:
                for dl in self._plugin.downloader():
                    # We get the file before we create directories. This allows the generator
                    # to get necessary info about what we're downloading before having to decide
                    # on what to name the directory.
                    filename, data = dl

                    # We allow the plugin to change directories in between files.
                    path = os.path.join(self.base_directory, self._plugin.directory())

                    if not os.path.isdir(path):
                        self.logger.info("Creating non-existent directory '{}'.".format(path))
                        os.makedirs(path)

                    with open(os.path.join(path, filename), "wb") as f:
                        f.write(data)

                    self._count += 1
                    
                    progress = self._plugin.progress()
                    if self._progress_bar is None:
                        if progress:
                            current, total = progress
                            self._progress_bar = ProgressBar(total=total,
                                units="files", singular="file")
                        else:
                            self._progress_bar = ProgressBar(units="files", singular="file")

                    self._progress_bar.update(1)
                    lrp.line = self._progress_bar.get("Last: " + filename)
                    lrp.flush()
        except Exception as e:
            self.logger.critical("An uncaught exception was raised while downloading.")
            if self._plugin.handle_exception(e) is True:
                pass
            else:
                raise e

    def finalize(self):
        if self._count:
            self.logger.info("Done! A total of {} files were downloaded.".format(self._count))

            # Check if finalize() has been overridden and call if it has.
            if self._plugin.finalize.__code__ is not BasePlugin.finalize.__code__:
                self.logger.info("Finalizing...")
                self._plugin.finalize()
        else:
            self.logger.info("No files were downloaded.")
