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

import re
import math
import PIL.Image
import io

from collections import namedtuple

"""
Class to descramble e-book pages served by BinB Reader using the provided descramble data.

A lot of it will look very ugly and unreadable, but that's done on purpose. Keeping it close
to how the JS does it makes it easier to compare the codes side-by-side and fix potential issues
in the future. Due to the obfuscated nature of the JS, variable names are stripped for the most
part, so I've taken the liberty of renaming those in this code whenever the purpose of a
variable is evident.

BinBDescrambler.decrypt() takes a file object and returns the data in bytes. If you need to
pass it bytes, wrap them in io.BytesIO first and it'll act similar to a file. The filename argument
is the filename of the image *as named by BinB*, not the desired filename. This filename is
used by the descramble algorithm to determine which of its 8 descrambling keys it should use.
"""

RE_SCRAMBLE_DATA = re.compile(r"^=([0-9]+)-([0-9]+)([-+])([0-9]+)-([-_0-9A-Za-z]+)$")

# Hardcoded array used to calculate the t, n, and p variables used for descrambling.
TNP_ARRAY = (-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, 62, -1, -1, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            61, -1, -1, -1, -1, -1, -1, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
            13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, -1, -1, -1, -1, 63, -1,
            26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
            45, 46, 47, 48, 49, 50, 51, -1, -1, -1, -1, -1)

# Named tuple to hold descramble data for each rectangle.
DescrambleRectangle = namedtuple("DescrambleRectangle", ["dst_x", "dst_y", "src_x", "src_y", "width", "height"])

class BinBDescrambler:
    def __init__(self, scramble_data):
        self._ctbl, self._ptbl = scramble_data
        self._h = []
        self._v = []
        self._padding = []
        self._src_str = []
        self._dst_str = []
        self._parse_scramble_data()

    @staticmethod
    def _calculate_descramble_index(filename):
        """
        Descramble data comes in arrays of 8 items, where which of the items
        should be used depends on the filename of the scrambled image.
        """
        c = 0
        p = 0
        for i, char in enumerate(filename):
            char = ord(char)
            if i % 2 == 0:
                p += char
            else:
                c += char
        p %= 8
        c %= 8

        return c, p

    def _parse_scramble_data(self):
        """Parse and validate the scramble data in the same manner the JS does."""
        for i in range(len(self._ctbl)):
            c = RE_SCRAMBLE_DATA.match(self._ctbl[i]).groups()
            p = RE_SCRAMBLE_DATA.match(self._ptbl[i]).groups()
            # groups() doesn't include group(0), so the indices below are all 1 less than in the JS.
            if c[0] != p[0] or c[1] != p[1] or c[3] != p[3] or c[2] != "+" or p[2] != "-":
                raise ValueError("Invalid scramble data.")

            self._h.append(int(c[0]))
            self._v.append(int(c[1]))
            self._padding.append(int(c[3]))
            if self._h[i] > 8 or self._v[i] > 8 or self._h[i] * self._v[i] > 64:
                raise ValueError("Invalid 'h' and 'v' values.")

            self._src_str.append(c[4])
            self._dst_str.append(p[4])
            target_len = self._h[i] + self._v[i] + self._h[i] * self._v[i]
            if len(self._src_str[i]) != target_len or len(self._dst_str[i]) != target_len:
                raise ValueError("'h' and 'v' do not match with 's_str' and 'd_str'.")

    def _generate_descramble_rectangles(self, filename, img_size):
        img_width, img_height = img_size
        c_index, p_index = self._calculate_descramble_index(filename)
        h = self._h[c_index]
        v = self._v[p_index]
        padding = self._padding[c_index]

        x = h * 2 * padding
        y = v * 2 * padding
        if not (img_width >= 64 + x and img_height >= 64 + y and img_height * img_width >= (320 + x) * (320 + y)):
            width = img_width
            height = img_height
        else:
            width = img_width - h * 2 * padding
            height = img_height - v * 2 * padding

        src_t, src_n, src_p = self._tnp(self._src_str[c_index], c_index)
        dst_t, dst_n, dst_p = self._tnp(self._dst_str[p_index], p_index)
        p = []
        for i in range(h * v):
            p.append(src_p[dst_p[i]])

        slice_width = math.floor((width + h - 1) / h)
        slice_height = math.floor((height + v - 1) / v)
        last_slice_width = width - (h - 1) * slice_width
        last_slice_height = height - (v - 1) * slice_height

        res = []
        for i in range(h * v):
            dst_column = i % h
            dst_row = math.floor(i / h)
            dst_x = padding + dst_column * (slice_width + 2 * padding) + (last_slice_width - slice_width if dst_n[dst_row] < dst_column else 0)
            dst_y = padding + dst_row * (slice_height + 2 * padding) + (last_slice_height - slice_height if dst_t[dst_column] < dst_row else 0)
            src_column = p[i] % h
            src_row = math.floor(p[i] / h)
            src_x = src_column * slice_width + (last_slice_width - slice_width if src_n[src_row] < src_column else 0)
            src_y = src_row * slice_height + (last_slice_height - slice_height if src_t[src_column] < src_row else 0)
            p_width = last_slice_width if dst_n[dst_row] == dst_column else slice_width
            p_height = last_slice_height if dst_t[dst_column] == dst_row else slice_height
            # For whatever reason, dst and src (called just d and s in the JS) switch places here.
            res.append(DescrambleRectangle(dst_x=src_x, dst_y=src_y, src_x=dst_x, src_y=dst_y, width=p_width, height=p_height))

        return width, height, res

    def _tnp(self, data, index):
        t = []
        n = []
        p = []

        h = self._h[index]
        v = self._v[index]

        for i in range(h):
            t.append(TNP_ARRAY[ord(data[i])])
        for i in range(v):
            n.append(TNP_ARRAY[ord(data[h + i])])
        for i in range(h * v):
            p.append(TNP_ARRAY[ord(data[h + v + i])])

        return t, n, p

    def descramble(self, filename, file, format="JPEG", **kwargs):
        img = PIL.Image.open(file, mode="r")
        img_arr = img.load()

        width, height, rectangles = self._generate_descramble_rectangles(filename, img.size)
        new = PIL.Image.new(img.mode, (width, height), color=255)
        new_arr = new.load()
        
        for rect in rectangles:
            for x in range(rect.width):
                for y in range(rect.height):
                    new_arr[x + rect.dst_x, y+rect.dst_y] = img_arr[x + rect.src_x, y + rect.src_y]
        
        image_data = io.BytesIO()
        if format == "JPEG":
            if "quality" not in kwargs:
                kwargs["quality"] = 95
            if "optimize" not in kwargs:
                kwargs["optimize"] = True
        new.save(image_data, format=format, **kwargs)

        return image_data.getvalue()
