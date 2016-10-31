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

There are two types of scrambling, which I simply refer to as type 1 and type 2. The former
seems to be the more common one, presumably the first one implemented, while the latter scramles
images in a more sophisticated way (i.e. not just fixed-size rectangles, but variable-sized ones
that also wrap around).

BinBDescrambler.decrypt() takes a file object and returns the data in bytes. If you need to
pass it bytes, wrap them in io.BytesIO first and it'll act similar to a file. The filename argument
is the filename of the image *as named by BinB*, not the desired filename. This filename is
used by the descramble algorithm to determine which of its 8 descrambling keys it should use.

"""

# TODO: Tests.

RE_SCRAMBLE_DATA = re.compile(r"^=([0-9]+)-([0-9]+)([-+])([0-9]+)-([-_0-9A-Za-z]+)$")

# Hardcoded array used to calculate the t, n, and p variables used for descrambling.
TNP_ARRAY = (-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, 62, -1, -1, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            61, -1, -1, -1, -1, -1, -1, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
            13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, -1, -1, -1, -1, 63, -1,
            26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
            45, 46, 47, 48, 49, 50, 51, -1, -1, -1, -1, -1)

# Descrambling key code types.
DESCRAMBLE_KEY_TYPE1 = 1 # ZRI2CR
DESCRAMBLE_KEY_TYPE2 = 2 # Z1U2CQ

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Named tuple to hold descramble data for each rectangle.
DescrambleRectangle = namedtuple("DescrambleRectangle", ["dst_x", "dst_y", "src_x", "src_y", "width", "height"])

# Parsed data type.
Type1Parsed = namedtuple("Type1Parsed", ["h", "v", "s_str", "d_str", "padding"])
Type2Parsed = namedtuple("Type2Parsed", ["ndx", "ndy", "pieces"])

class BinBDescrambler:
    def __init__(self, scramble_data):
        self._types = []
        self._ctbl, self._ptbl = scramble_data
        
        # Type 1 variables.
        self._t1_parsed = []
        # Type 2 variables.
        self._t2_parsed_ctbl = []
        self._t2_parsed_ptbl = []

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
        """Parse and validate the scramble data in a similar manner to the JS code."""
        for i in range(len(self._ctbl)):
            if self._ctbl[i][0] == "=" and self._ptbl[i][0] == "=":
                # Type 1
                self._types.append(DESCRAMBLE_KEY_TYPE1)
                self._t1_parsed.append(self._parse_type_1(self._ctbl[i], self._ptbl[i]))
            elif self._ctbl[i][0].isdigit() and self._ptbl[i][0].isdigit():
                self._types.append(DESCRAMBLE_KEY_TYPE2)
                c_parsed = self._parse_type_2(self._ctbl[i])
                p_parsed = self._parse_type_2(self._ptbl[i])
                if c_parsed.ndx != p_parsed.ndx or c_parsed.ndy != p_parsed.ndy:
                    raise ValueError("ctbl and ptbl of type 2 do not match.")
                self._t2_parsed_ctbl.append(c_parsed)
                self._t2_parsed_ptbl.append(p_parsed)
            else:
                raise ValueError("Unknown descrambling key type: " +
                    str((self._ctbl[i], self._ptbl[i])))

    def _parse_type_1(self, ctbl, ptbl):
        c = RE_SCRAMBLE_DATA.match(ctbl).groups()
        p = RE_SCRAMBLE_DATA.match(ptbl).groups()
        # groups() doesn't include group(0), so the indices below are all 1 less than in the JS.
        if c[0] != p[0] or c[1] != p[1] or c[3] != p[3] or c[2] != "+" or p[2] != "-":
            raise ValueError("Invalid scramble data.")

        h = int(c[0])
        v = int(c[1])
        padding = int(c[3])
        if h > 8 or v > 8 or h * v > 64:
            raise ValueError("Invalid 'h' and 'v' values.")

        s_str = c[4]
        d_str = p[4]
        target_len = h + v + h * v
        if len(s_str) != target_len or len(d_str) != target_len:
            raise ValueError("'h' and 'v' do not match with 's_str' and 'd_str'.")

        return Type1Parsed(h=h, v=v, s_str=s_str, d_str=d_str, padding=padding)

    def _parse_type_2(self, key):
        def decode_t2_key_char(char):
            try:
                c = ALPHABET.index(char)
                b = 1
            except ValueError:
                c = ALPHABET.lower().index(char)
                b = 0

            return b + c * 2
        
        # Type 2
        split_key = key.split("-")
        if len(split_key) != 3:
            raise ValueError("Invalid format of a type 2 key.")
        
        ndx = int(split_key[0])
        ndy = int(split_key[1])
        data = split_key[2]
        if len(data) != ndx*ndy*2:
            raise ValueError("Invalid key. Key data length does not match the rest.")

        f = (ndx - 1) * (ndy - 1) - 1
        g = f + (ndx - 1)
        h = g + (ndy - 1)
        j = h + 1
        pieces = []
        for i in range(ndx*ndy):
            piece = {}
            piece["x"] = decode_t2_key_char(data[i*2])
            piece["y"] = decode_t2_key_char(data[i*2+1])
            if i <= f:
                piece["width"] = 2
                piece["height"] = 2
            elif i <= g:
                piece["width"] = 2
                piece["height"] = 1
            elif i <= h:
                piece["width"] = 1
                piece["height"] = 2
            elif i <= j:
                piece["width"] = 1
                piece["height"] = 1
            pieces.append(piece)

        return Type2Parsed(ndx=ndx, ndy=ndy, pieces=pieces)

    def _t1_generate_descramble_rectangles(self, c_index, p_index, img_size):
        def _tnp(data, h, v):
            t = []
            n = []
            p = []

            for i in range(h):
                t.append(TNP_ARRAY[ord(data[i])])
            for i in range(v):
                n.append(TNP_ARRAY[ord(data[h + i])])
            for i in range(h * v):
                p.append(TNP_ARRAY[ord(data[h + v + i])])

            return t, n, p
        
        # Get the right tuples out to avoid indexing every time.
        c_parsed = self._t1_parsed[c_index]
        p_parsed = self._t1_parsed[p_index]

        img_width, img_height = img_size
        h = c_parsed.h
        v = p_parsed.v
        padding = c_parsed.padding

        x = h * 2 * padding
        y = v * 2 * padding
        if not (img_width >= 64 + x and img_height >= 64 + y and img_height * img_width >= (320 + x) * (320 + y)):
            width = img_width
            height = img_height
        else:
            width = img_width - h * 2 * padding
            height = img_height - v * 2 * padding

        src_t, src_n, src_p = _tnp(c_parsed.s_str, h, v)
        dst_t, dst_n, dst_p = _tnp(p_parsed.d_str, h, v)
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

    def _t2_generate_descramble_rectangles(self, c_index, p_index, img_size):
        img_width, img_height = img_size
        res = []
        if img_width >= 64 and img_height >= 64 and img_width * img_height >= 320 * 320:
            e = img_width - (img_width % 8)
            f = math.floor((e - 1) / 7) - math.floor((e - 1) / 7) % 8
            g = e - f * 7
            h = img_height - (img_height % 8)
            j = math.floor((h - 1) / 7) - math.floor((h - 1) / 7) % 8
            k = h - j * 7
            
            c_parsed = self._t2_parsed_ctbl[c_index]
            p_parsed = self._t2_parsed_ptbl[p_index]
            for i in range(len(c_parsed.pieces)):
                c_piece = c_parsed.pieces[i]
                p_piece = p_parsed.pieces[i]
                src_x = math.floor(c_piece["x"] / 2) * f + (c_piece["x"] % 2) * g
                src_y = math.floor(c_piece["y"] / 2) * j + (c_piece["y"] % 2) * k
                dst_x = math.floor(p_piece["x"] / 2) * f + (p_piece["x"] % 2) * g
                dst_y = math.floor(p_piece["y"] / 2) * j + (p_piece["y"] % 2) * k
                width = math.floor(c_piece["width"] / 2) * f + (c_piece["width"] % 2) * g
                height = math.floor(c_piece["height"] / 2) * j + (c_piece["height"] % 2) * k
                res.append(DescrambleRectangle(src_x=src_x, src_y=src_y, dst_x=dst_x, dst_y=dst_y, width=width, height=height))

            e = f * (c_parsed.ndx - 1) + g
            h = j * (c_parsed.ndy - 1) + k
            if e < img_width:
                res.append(DescrambleRectangle(src_x=e, src_y=0, dst_x=e, dst_y=0, width=img_width - e, height=h))
            if h < img_height:
                res.append(DescrambleRectangle(src_x=0, src_y=h, dst_x=0, dst_y=h, width=img_width, height=img_height - h))
        else:
            # The commented code below is what the JS does, but I'm pretty sure that's just a way
            # of returning an error, so I'm just raising an exception instead. Too lazy to confirm.
            # res = [DescrambleRectangle(dst_x=0, dst_y=0, src_x=0, src_y=0, width=img_width, height=img_height)]
            raise ValueError("Invalid input image dimensions.")
        
        return img_width, img_height, res

    def descramble(self, filename, file, format="JPEG", **kwargs):
        img = PIL.Image.open(file, mode="r")
        img_arr = img.load()

        c_index, p_index = self._calculate_descramble_index(filename)
        key_type = self._types[c_index]
        if key_type == DESCRAMBLE_KEY_TYPE1:
            width, height, rectangles = self._t1_generate_descramble_rectangles(c_index, p_index, img.size)
        elif key_type == DESCRAMBLE_KEY_TYPE2:
            width, height, rectangles = self._t2_generate_descramble_rectangles(c_index, p_index, img.size)
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
