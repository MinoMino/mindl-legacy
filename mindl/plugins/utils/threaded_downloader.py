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

import threading
import queue
import time

from mindl import BasePlugin

class ThreadedDownloaderPlugin(BasePlugin):
    def __init__(self, thread_count=10):
        self._thread_count = thread_count
        self._threads = []
        self.stop_event = threading.Event()
        # It should be safe to use a list here, but just in case we'll use Queue.
        self._downloads = queue.Queue()
        self.download_counter = 0
        self._errors = 0 # Number of errors while downloading files.
        self._errors_lock = threading.Lock()
        self._thread_items = None

    def got_download(self, item):
        self._downloads.put(item)

    def downloader(self):
        # Start all the threads and start downloading immediately.
        self._start_threads()
        
        try:
            while not self._done():
                # Try until we either get a download or threads are dead.
                try:
                    filename, data = self._downloads.get(timeout=0.25)
                except queue.Empty:
                    if not self._are_threads_alive():
                        # Threads are all dead. Assert we have all downloads we should have.
                        if self._expected != -1 and self.download_counter != self._expected:
                            raise RuntimeError("All downloader threads are dead, but not all downloads have finished.")
                        # Otherwise we're just fine.
                        break
                    else:
                        continue

                self.download_counter += 1
                yield filename, data
        except KeyboardInterrupt:
            self.logger.info("Download interrupted! Please wait for threads to stop...")
            self.stop_event.set()
            while self._are_threads_alive():
                time.sleep(0.1)

    def download_many(self, items):
        """The thread target that will download many files and put results in our queue using got_download()."""
        raise NotImplementedError("The downloader itself needs to be implemented.")

    def distribute_items(self, items, expected_downloads=-1):
        self._expected = expected_downloads
        split_items = [[] for i in range(self._thread_count)]
        for i, item in enumerate(items):
            split_items[i % self._thread_count].append(item)

        self._thread_items = split_items

    def _start_threads(self):
        """Distribute items to threads as equally as possible, then start threads."""
        # Start threads.
        for i in range(self._thread_count):
            if self._thread_items is None:
                args = ()
            else:
                args = (self._thread_items[i],)
            self._threads.append(threading.Thread(target=self.download_many, args=args))
            self._threads[i].start()
            time.sleep(0.1)

    def _done(self):
        if self._expected == -1:
            # expected_downloads not set, so we're not done until threads die.
            return False
        elif self.download_counter > self._expected:
            raise RuntimeError("Got more downloads than expected.")
        else:
            return self.download_counter == self._expected

    def _are_threads_alive(self):
        for thread in self._threads:
            if thread.is_alive():
                return True

        return False
