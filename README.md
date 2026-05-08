# Cricket Dude

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Cricket Dude is a lightweight terminal UI for checking live cricket scores, recent results, upcoming fixtures, and IPL matches.

## Features

* Live, recent, upcoming, and IPL views.
* Rich-powered terminal interface with keyboard navigation.
* Score view refreshes every 60 seconds by default while viewing matches.
* Reuses cached API responses when switching between related views.
* Manual refresh with `R` when you want fresh data immediately.
* Reuses HTTP connections for lower refresh overhead.
* Optional HTML scrape mode for scoreboard pages you are allowed to fetch.
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

Optional API usage controls:

```powershell
$env:CRICKET_REFRESH_SECONDS="120"
$env:CRICKET_CACHE_SECONDS="120"
```

`CRICKET_REFRESH_SECONDS` controls how often the active screen tries to refresh. `CRICKET_CACHE_SECONDS` controls how long live/recent/IPL score data is reused before another API request is allowed. Upcoming schedules are cached for 5 minutes.

## Scrape Mode

Scrape mode is opt-in and should only be used for pages you are allowed to request. It does not bypass logins, bot protection, paywalls, or site restrictions.

```powershell
$env:CRICKET_SOURCE="scrape"
$env:CRICKET_SCRAPE_URL="https://example.com/live-score"
$env:CRICKET_SCRAPE_MATCH_SELECTOR=".match-card"
$env:CRICKET_SCRAPE_TEAM_ONE_SELECTOR=".team-a"
$env:CRICKET_SCRAPE_TEAM_TWO_SELECTOR=".team-b"
$env:CRICKET_SCRAPE_SCORE_SELECTOR=".score"
$env:CRICKET_SCRAPE_STATUS_SELECTOR=".status"
$env:CRICKET_REFRESH_SECONDS="10"
$env:CRICKET_CACHE_SECONDS="10"
```

Required scrape settings are `CRICKET_SCRAPE_URL`, `CRICKET_SCRAPE_MATCH_SELECTOR`, and `CRICKET_SCRAPE_SCORE_SELECTOR`. Team and status selectors are optional. In scrape mode, Live and IPL views show scraped live cards; Recent and Upcoming stay empty because generic HTML pages do not expose reliable schedule semantics.

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
* R: refresh the current view immediately.
* Q / Esc: return to the main menu or exit.
* Ctrl+C: quit immediately.

## Files

* `main.py`: API client, terminal input handling, and Rich UI rendering.
* `setup.py`: local package installation metadata.
* `.gitignore`: Python cache and environment ignores.

## License

Distributed under the MIT License.
