from setuptools import setup


setup(
    name='neptune',
    version='0.1',
    description='IPython frontend',
    author='Jan Hermann',
    author_email='dev@hermann.in',
    url='https://github.com/azag0/neptune',
    packages=['neptune'],
    scripts=['scripts/neptune'],
    classifiers=[
        'Development Status :: 1 - Planning',
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
        'websockets',
        'mypy_extensions',
        'ansi2html',
        'misaka',
        'aiohttp',
        'pygments',
    ],
)
