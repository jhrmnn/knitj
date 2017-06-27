from setuptools import setup


setup(
    name='thebe',
    version='0.1',
    description='Alternative Jupyter front-end',
    author='Jan Hermann',
    author_email='dev@hermann.in',
    url='https://github.com/azag0/thebe',
    packages=['thebe'],
    scripts=['scripts/thebe'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Framework :: IPython',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)',
        'Natural Language :: English',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3.6',
        'Topic :: Utilities',
    ],
    license='Mozilla Public License 2.0',
    install_requires=[
        'watchdog',
        'ipykernel',
        'jupyter-client',
        'mypy_extensions',
        'ansi2html',
        'misaka',
        'aiohttp',
        'pygments',
        'Jinja2',
        'beautifulsoup4',
    ],
)
