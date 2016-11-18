# mindl
A plugin-based downloading tool for Python 3.5 and above.

**NOTE**: I'm currently in the process of rewriting this in Go. Check the [wiki](https://github.com/MinoMino/mindl/wiki)
for the reasoning. Once the rewrite is in a decent state, it will replace the content here. This version will be moved
to a new repository called "mindl-legacy" or something along those lines.

It was written primarily for the purpose of downloading e-books from sites that use HTML5 readers, which is
why some plugins require Selenium and PhantomJS, but it is not limited to that.

If you've got some other HTML5 reader you want supported and you can provide a sample, I will consider writing a plugin for it.
Open an issue here or send me an e-mail about it. I cannot promise a plugin that downloads from their API if the images are
scrambled because reverse engineering heavily obfuscated JavaScript can be hard and very time consuming, but the PhantomJS approach is
usually fairly easy in contrast.

## Installation
* Install [Python 3.5+](https://www.python.org/downloads/)
* If you're planning to use it for eBookJapan, download [PhantomJS](http://phantomjs.org/download.html) and put the executable in your PATH. If you're on
Linux, remember to make it executable as well.
* Run the following command to install mindl:
`python -m pip install git+https://github.com/MinoMino/mindl.git`
* You should now be able to run mindl from the command line. See below for details about usage.

**NOTE**: If you're not on a virtual environment or something similar, you might need to run `pip` as root.

## Usage
```
usage: mindl [-h] [-o KEY=VALUE] [-v] [-d] [-p PLUGIN] [-f PATH]
             [-D DIRECTORY]
             [URL [URL ...]]

A plugin-based downloader.

positional arguments:
  URL                   the URL to download from

optional arguments:
  -h, --help            show this help message and exit
  -o KEY=VALUE, --option KEY=VALUE
                        a key-value pair to be passed to the plugin to define
                        its options
  -v, --verbose         makes the logger output debugging strings
  -d, --defaults        makes the plugin use default values for options if it
                        can instead of prompting
  -p PLUGIN, --plugin PLUGIN
                        explicitly set which plugin should handle the URL in
                        the case where two or more plugins can handle the same URL
  -f PATH, --file PATH  the path to a text file containing URLs to be
                        processed, separated by lines
  -D DIRECTORY, --directory DIRECTORY
                        the directory in which the downloads will go to
                        ('downloads' by default)
```

To run it, use Python's `-m` argument to run modules: `python -m mindl [...]`

### Example
```
mino$ python -m mindl -o username=some@mail.com -o password=mypassword123 "https://br.ebookjapan.jp/br/reader/viewer/view.html?sessionid=[...]&keydata=[...]&shopID=eBookJapan"
(06:20 INFO) URL is being handled by plugin: eBookJapan v0.1
(06:20 INFO) Starting download...
[...]
(06:27 INFO) Done! A total of 206 files were downloaded.
(06:27 INFO) Finalizing...
```

**Make sure you use double quotes around each URL, or the console will interpret the ampersands as multiple console commands
instead of part of the URL(s).**

If the plugin requires any options to be configured, you can pass them with `-o` like in the above example, but you can
also just run mindl without passing them and have it prompt you for them later.

## Supported Sites
### eBookJapan
Uses Selenium and PhantomJS to navigate through the HTML5 reader, sequentially reading the pages off the canvases.
It's somewhat slow because of this. Make sure the PhantomJS executable is in your PATH environment variable.

Needs e-mail and password supplied so that it can log on.

##### Usage
Open the reader and you should get a URL like
`https://br.ebookjapan.jp/br/reader/viewer/view.html?sessionid=[...]&keydata=[...]&shopID=eBookJapan`
which is the one you need to pass to mindl. EBJ has protection against account sharing, so make sure
you both get the URL *and* use mindl from the same IP address.

### BookLive
Directly interacts with the API and descrambles the images using [pillow](https://python-pillow.org/) for image
processing. Uses threads to download and descramble images, so it's very fast. It can also zip the book for you
after downloading and descrambling everything.

If you do not supply e-mail and password, it will not log on and instead download the trial pages. Make sure
you pass it the credentials if you own the book you wish to download.

##### Usage
The URLs handled by this plugin:
* Product pages: `https://booklive.jp/product/index/title_id/[...]/vol_no/[...]`
* Reader: `https://booklive.jp/bviewer/?cid=[...]&rurl=[...]`

### AnimateBookstore
Based on the same reader used on BookLive, so it works virtually the same way. I don't have a paid book owned there myself
so I can't actually confirm it works like it should for paid books, but I believe it should. If you use it for one,
I'd appreciate if you could tell me whether or not it works.

You can run it without supplying credentials, but some trials still require them, so I'd recommend just supplying them
whenever you can. You might get a warning about books being trials when they're not, but it's because I don't have a
good way to tell whether or not it's a trial without actually having a book bought there. Just pay attention to the
page count to tell whether or not you're getting the full book.

##### Usage
The URLs handled by this plugin:
* Product pages: `https://www.animatebookstore.com/products/detail.php?product_id=[...]`
* Reader: `http://www.animatebookstore.com/bookview/?u0=[...]&cid=[...]`
