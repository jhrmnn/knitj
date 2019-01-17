# Knitj

![python](https://img.shields.io/pypi/pyversions/knitj.svg)
[![pypi](https://img.shields.io/pypi/v/knitj.svg)](https://pypi.org/project/knitj/)
[![commits since](https://img.shields.io/github/commits-since/jhrmnn/knitj/latest.svg)](https://github.com/jhrmnn/knitj/releases)
[![last commit](https://img.shields.io/github/last-commit/jhrmnn/knitj.svg)](https://github.com/jhrmnn/knitj/commits/master)
[![license](https://img.shields.io/github/license/jhrmnn/knitj.svg)](https://github.com/jhrmnn/knitj/blob/master/LICENSE)
[![code style](https://img.shields.io/badge/code%20style-black-202020.svg)](https://github.com/ambv/black)

Knitj is an alternative front-end to Jupyter kernels. Inspired by [knitr](https://yihui.name/knitr/) and [R Markdown](http://rmarkdown.rstudio.com), Knitj renders a mix of markdown and source code into HTML by evaluating the code in a Jupyter kernel.

In addition to a one-off conversion, Knitj can serve the HTML document via HTTP and watch the source file for changes. When the source file is changed, Knitj reevaluates only the changed bits (defined by boundaries between markdown and source code), and pushes the updates into the HTML document via WebSocket.

## Example

Either of the two following files renders into the same HTML document below with

```bash
knitj $SOURCE >$SOURCE.html
```

~~~markdown
```python
#::hide
import numpy as np
from matplotlib import pyplot as plt
%matplotlib inline
```

## Example

Let's plot

$$ f(x)=\frac{\sin x}x $$

```python
x = np.linspace(-20, 20, 200)
plt.plot(x, np.sin(x)/x)
```
~~~

```python
# ::hide
import numpy as np
from matplotlib import pyplot as plt
# ::%matplotlib inline

# ::>
# ## Example
#
# Let's plot
#
# $$ f(x)=\frac{\sin x}x $$

x = np.linspace(-20, 20, 200)
plt.plot(x, np.sin(x)/x)
```

![](docs/static/example.png)

Alternatively, one can start the Knitj server, which starts watching the source file for changes and opens a browser window with the rendered and live-updated HTML document

```
$ knitj --server test.py
[22:19:14.718] INFO:knitj: Entered Knitj
[22:19:14.722] INFO:knitj.document: File change: 3/0 new cells, 0 dropped
[22:19:14.732] INFO:knitj.document: 2 code cells loaded from output
[22:19:14.732] INFO:knitj.kernel: Starting kernel...
[22:19:15.145] INFO:knitj.kernel: Kernel started
[22:19:15.160] INFO:knitj.knitj: Started web server on port 8081
[22:19:15.441] INFO:knitj.knitj: Started broadcasting to browsers
[22:19:15.462] INFO:knitj.source: Started watching file test.md for changes
[22:19:15.881] INFO:knitj.webserver: Browser connected: 4542074160
[22:19:41.477] INFO:knitj.document: File change: 1/3 new cells, 1 dropped
[22:19:41.683] INFO:knitj.document: 72fea2: Got an error
[22:19:41.698] INFO:knitj.document: 72fea2: Cell done
[22:19:41.716] INFO:knitj.document: 72fea2: Got an error execution reply
^C[22:19:46.179] INFO:knitj.webserver: Closing websockets
[22:19:46.180] INFO:knitj.webserver: Browser disconnected: 4542074160
[22:19:46.181] INFO:knitj.kernel: Kernel shut down
[22:19:46.186] INFO:knitj: Leaving Knitj
```

## Installing

Install and update using [Pip](https://pip.pypa.io/en/stable/quickstart/).

```
pip install -U knitj
```

The following dependencies are installed:

-   [Jupyter Client](https://github.com/jupyter/jupyter_client) for communicating with the Jupyter kernels
-   [Watchdog](https://pythonhosted.org/watchdog/) for watching a file for changes
-   [ansi2html](https://github.com/ralphbean/ansi2html) for converting ANSI color codes into HTML
-   [Misaka](http://misaka.61924.nl) for rendering Markdown
-   [aiohttp](http://aiohttp.readthedocs.io) for running a http and WebSocket server
-   [Pygments](http://pygments.org) for syntax highlighting
-   [Jinja](http://jinja.pocoo.org) for HTML templates
-   [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) for parsing HTML

To use Knitj, you also need some Jupyter kernel on your system. If you don’t have one, you can get the IPython kernel with

```
pip install ipykernel
```

## Usage

```
usage: knitj [-h] [-s] [-f FORMAT] [-o FILE] [-k KERNEL] [-b BROWSER] [-n]
             [FILE]

positional arguments:
  FILE                  input file

optional arguments:
  -h, --help            show this help message and exit
  -s, --server          run in server mode
  -f FORMAT, --format FORMAT
                        input format
  -o FILE, --output FILE
                        output HTML file
  -k KERNEL, --kernel KERNEL
                        Jupyter kernel to use
  -b BROWSER, --browser BROWSER
                        browser to open
  -n, --no-browser      do not open a browser
```
