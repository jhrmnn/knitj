# -*- coding: utf-8 -*-
from distutils.core import setup

packages = \
['knitj', 'knitj.jupyter_messaging', 'knitj.jupyter_messaging.content']

package_data = \
{'': ['*'],
 'knitj': ['client/.eslintrc',
           'client/.eslintrc',
           'client/.eslintrc',
           'client/.eslintrc',
           'client/.gitignore',
           'client/.gitignore',
           'client/.gitignore',
           'client/.gitignore',
           'client/package-lock.json',
           'client/package-lock.json',
           'client/package-lock.json',
           'client/package-lock.json',
           'client/package.json',
           'client/package.json',
           'client/package.json',
           'client/package.json',
           'client/static/*',
           'client/templates/*']}

install_requires = \
['Jinja2>=2.10,<3.0',
 'aiohttp>=3.4,<4.0',
 'ansi2html>=1.5,<2.0',
 'beautifulsoup4>=4.6,<5.0',
 'jupyter-client>=5.2,<6.0',
 'misaka>=2.1,<3.0',
 'pygments>=2.2,<3.0',
 'pyyaml>=3.13,<4.0',
 'watchdog>=0.9.0,<0.10.0']

entry_points = \
{'console_scripts': ['knitj = knitj.cli:main']}

setup_kwargs = {
    'name': 'knitj',
    'version': '0.3.0',
    'description': 'Alternative Jupyter front-end',
    'long_description': "# Knitj\n\n![python](https://img.shields.io/pypi/pyversions/knitj.svg)\n[![pypi](https://img.shields.io/pypi/v/knitj.svg)](https://pypi.org/project/knitj/)\n[![commits since](https://img.shields.io/github/commits-since/jhrmnn/knitj/latest.svg)](https://github.com/jhrmnn/knitj/releases)\n[![last commit](https://img.shields.io/github/last-commit/jhrmnn/knitj.svg)](https://github.com/jhrmnn/knitj/commits/master)\n[![license](https://img.shields.io/github/license/jhrmnn/knitj.svg)](https://github.com/jhrmnn/knitj/blob/master/LICENSE)\n[![code style](https://img.shields.io/badge/code%20style-black-202020.svg)](https://github.com/ambv/black)\n\nKnitj is an alternative front-end to Jupyter kernels. Inspired by [knitr](https://yihui.name/knitr/) and [R Markdown](http://rmarkdown.rstudio.com), Knitj renders a mix of markdown and source code into HTML by evaluating the code in a Jupyter kernel.\n\nIn addition to a one-off conversion, Knitj can serve the HTML document via HTTP and watch the source file for changes. When the source file is changed, Knitj reevaluates only the changed bits (defined by boundaries between markdown and source code), and pushes the updates into the HTML document via WebSocket.\n\n## Example\n\nEither of the two following files renders into the same HTML document below with\n\n```bash\nknitj $SOURCE >$SOURCE.html\n```\n\n~~~markdown\n```python\n#::hide\nimport numpy as np\nfrom matplotlib import pyplot as plt\n%matplotlib inline\n```\n\n## Example\n\nLet's plot\n\n$$ f(x)=\\frac{\\sin x}x $$\n\n```python\nx = np.linspace(-20, 20, 200)\nplt.plot(x, np.sin(x)/x)\n```\n~~~\n\n```python\n# ::hide\nimport numpy as np\nfrom matplotlib import pyplot as plt\n# ::%matplotlib inline\n\n# ::>\n# ## Example\n#\n# Let's plot\n#\n# $$ f(x)=\\frac{\\sin x}x $$\n\nx = np.linspace(-20, 20, 200)\nplt.plot(x, np.sin(x)/x)\n```\n\n![](docs/static/example.png)\n\nAlternatively, one can start the Knitj server, which starts watching the source file for changes and opens a browser window with the rendered and live-updated HTML document\n\n```\n$ knitj --server test.py\n[22:19:14.718] INFO:knitj: Entered Knitj\n[22:19:14.722] INFO:knitj.document: File change: 3/0 new cells, 0 dropped\n[22:19:14.732] INFO:knitj.document: 2 code cells loaded from output\n[22:19:14.732] INFO:knitj.kernel: Starting kernel...\n[22:19:15.145] INFO:knitj.kernel: Kernel started\n[22:19:15.160] INFO:knitj.knitj: Started web server on port 8081\n[22:19:15.441] INFO:knitj.knitj: Started broadcasting to browsers\n[22:19:15.462] INFO:knitj.source: Started watching file test.md for changes\n[22:19:15.881] INFO:knitj.webserver: Browser connected: 4542074160\n[22:19:41.477] INFO:knitj.document: File change: 1/3 new cells, 1 dropped\n[22:19:41.683] INFO:knitj.document: 72fea2: Got an error\n[22:19:41.698] INFO:knitj.document: 72fea2: Cell done\n[22:19:41.716] INFO:knitj.document: 72fea2: Got an error execution reply\n^C[22:19:46.179] INFO:knitj.webserver: Closing websockets\n[22:19:46.180] INFO:knitj.webserver: Browser disconnected: 4542074160\n[22:19:46.181] INFO:knitj.kernel: Kernel shut down\n[22:19:46.186] INFO:knitj: Leaving Knitj\n```\n\n## Installing\n\nInstall and update using [Pip](https://pip.pypa.io/en/stable/quickstart/).\n\n```\npip install -U knitj\n```\n\nThe following dependencies are installed:\n\n-   [Jupyter Client](https://github.com/jupyter/jupyter_client) for communicating with the Jupyter kernels\n-   [Watchdog](https://pythonhosted.org/watchdog/) for watching a file for changes\n-   [ansi2html](https://github.com/ralphbean/ansi2html) for converting ANSI color codes into HTML\n-   [Misaka](http://misaka.61924.nl) for rendering Markdown\n-   [aiohttp](http://aiohttp.readthedocs.io) for running a http and WebSocket server\n-   [Pygments](http://pygments.org) for syntax highlighting\n-   [Jinja](http://jinja.pocoo.org) for HTML templates\n-   [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) for parsing HTML\n\nTo use Knitj, you also need some Jupyter kernel on your system. If you don’t have one, you can get the IPython kernel with\n\n```\npip install ipykernel\n```\n\n## Usage\n\n```\nusage: knitj [-h] [-s] [-f FORMAT] [-o FILE] [-k KERNEL] [-b BROWSER] [-n]\n             [FILE]\n\npositional arguments:\n  FILE                  input file\n\noptional arguments:\n  -h, --help            show this help message and exit\n  -s, --server          run in server mode\n  -f FORMAT, --format FORMAT\n                        input format\n  -o FILE, --output FILE\n                        output HTML file\n  -k KERNEL, --kernel KERNEL\n                        Jupyter kernel to use\n  -b BROWSER, --browser BROWSER\n                        browser to open\n  -n, --no-browser      do not open a browser\n```\n",
    'author': 'Jan Hermann',
    'author_email': 'dev@jan.hermann.name',
    'url': 'https://github.com/jhrmnn/knitj',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'entry_points': entry_points,
    'python_requires': '>=3.6,<4.0',
}


setup(**setup_kwargs)
