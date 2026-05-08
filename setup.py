from pathlib import Path

from setuptools import setup


ROOT = Path(__file__).parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

setup(
    name="cricket-dude",
    version="1.1.0",
    description="A fast terminal UI for live cricket scores.",
    long_description=README,
    long_description_content_type="text/markdown",
    author="mrduhlol",
    py_modules=["main"],
    python_requires=">=3.10",
    install_requires=[
        "rich>=13.0.0",
        "requests>=2.28.0",
    ],
    entry_points={
        "console_scripts": [
            "cricket-dude=main:main",
        ],
    },
)
