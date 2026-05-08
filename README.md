# Cricket Dude

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Cricket Dude is a lightweight terminal UI for checking live cricket scores, recent results, upcoming fixtures, and IPL matches.

## Features

* Live, recent, upcoming, and IPL views.
* Rich-powered terminal interface with keyboard navigation.
* Works out of the box with a built-in free live-score source.
* Score view refreshes every 5 seconds by default while viewing matches.
* Bypasses stale page caches when refreshing live scores.
* Manual refresh with `R` when you want fresh data immediately.
* Reuses HTTP connections for lower refresh overhead.

## Setup

Install the package locally:

```bash
pip install .
```

Run the app:

```bash
cricket-dude
```

Or run it directly:

```bash
python main.py
```

Cricket Dude uses a built-in Cricbuzz live-scores reader, so users do not need to enter credentials or scoreboard URLs.

Optional refresh controls:

```powershell
$env:CRICKET_REFRESH_SECONDS="5"
$env:CRICKET_CACHE_SECONDS="5"
```

`CRICKET_REFRESH_SECONDS` controls how often the active screen refreshes. `CRICKET_CACHE_SECONDS` controls how long fetched score data is reused when moving between screens. Active score screens force a fresh fetch on each timed refresh.

## Controls

* Up / Down: move through menu options.
* Enter / Space: open the selected view.
* R: refresh the current view immediately.
* Q / Esc: return to the main menu or exit.
* Ctrl+C: quit immediately.

## Files

* `main.py`: built-in live-score reader, terminal input handling, and Rich UI rendering.
* `setup.py`: local package installation metadata.
* `.gitignore`: Python cache and environment ignores.

## License

Distributed under the MIT License.
