# mindl
A plugin-based downloading tool. It was written with Python 3.5+ in mind, so while it's likely that at least 3.4 works,
it's possible I've used new stuff that could potentially make it incompatible.

It was written for the purpose of downloading e-books using PhantomJS from sites that use HTML5 readers, which is
why it requires Selenium. The framework can however obviously be used for anything.

As of right now, it only works with eBookJapan. If you've got some other HTML5 reader you want supported and you
can provide a sample, I will consider writing a plugin for it. Open an issue here or send me an e-mail about it.

## Installation
* Install Python 3.5+
* Download PhantomJS from [here](http://phantomjs.org/download.html) and put the executable in your PATH. If you're on
Linux, remember to make it executable as well.
* Run the following command to install mindl:
`python -m pip install git+https://github.com/MinoMino/mindl.git#egg=mindl`
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

## Example
```
mino$ python -m mindl -o email=some@mail.com -o password=mypassword123 "https://br.ebookjapan.jp/br/reader/viewer/view.html?sessionid=[...]&keydata=[...]&shopID=eBookJapan"
(06:20 INFO) URL is being handled by plugin: eBookJapan v0.1
(06:20 INFO) Starting download...
[...]
(06:27 INFO) Done! A total of 206 were downloaded.
(06:27 INFO) Finalizing...
```

**Make sure you use double quotes around each URL, or the console will interpret the ampersands as multiple console commands
instead of part of the URL(s).**

In the above example I've put it my credentials using the `-o` argument, but if you leave one or both out,
you will instead be prompted for the missing options at launch.
