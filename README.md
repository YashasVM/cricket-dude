# Cricket Dude

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Cricket Dude is a lightweight terminal UI for checking live cricket scores, recent results, upcoming fixtures, and IPL matches.

## Features

* Live, recent, upcoming, and IPL views.
* Rich-powered terminal interface with keyboard navigation.
* Score refreshes every 15 seconds while viewing matches.
* Reuses HTTP connections for lower refresh overhead.
* Keeps API credentials out of source code.

## Setup

Install the package locally:

```bash
pip install .
```

Get an API key from [CricketData.org](https://cricketdata.org/) and set it in your environment.

Windows PowerShell:

```powershell
$env:CRICKET_API_KEY="your-key-here"
```

Linux/macOS:

```bash
export CRICKET_API_KEY="your-key-here"
```

Run the app:

```bash
cricket-dude
```

Or run it directly:

```bash
python main.py
```

## Controls

* Up / Down: move through menu options.
* Enter / Space: open the selected view.
* Q / Esc: return to the main menu or exit.
* Ctrl+C: quit immediately.

## Files

* `main.py`: API client, terminal input handling, and Rich UI rendering.
* `setup.py`: local package installation metadata.
* `.gitignore`: Python cache and environment ignores.

## License

Distributed under the MIT License.
