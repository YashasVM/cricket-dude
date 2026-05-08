from setuptools import setup

setup(
    name='cricket-dude',
    version='1.0.0',
    description='A high-performance terminal UI for live cricket scores.',
    author='mrduhlol',
    py_modules=['main'],
    install_requires=[
        'rich>=13.0.0',
        'requests>=2.28.0',
    ],
    entry_points={
        'console_scripts': [
            'cricket-dude = main:main',
        ],
    },
)