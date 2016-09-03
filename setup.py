#!/usr/bin/env python

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

import mindl

from distutils.core import setup

setup(name="mindl",
      version=mindl.__version__,
      description="A plugin-based downloading tool.",
      author="Mino",
      author_email="mino@minomino.org",
      packages=["mindl"],
      install_requires=["requests", "selenium"],
      classifiers = [
              "Programming Language :: Python",
              "Programming Language :: Python :: 3",
              "Development Status :: 4 - Beta",
              "Environment :: Console",
              "Operating System :: Microsoft :: Windows",
              "Operating System :: POSIX",
              "Topic :: Multimedia :: Graphics",
              "Topic :: Utilities",
              "Topic :: Internet :: WWW/HTTP",
              ]
     )