from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Protocol
from urllib.parse import urlparse

import requests
from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

try:
    import select
    import termios
    import tty

    IS_WINDOWS = False
except ImportError:
    import msvcrt

    IS_WINDOWS = True


API_KEY_ENV = "CRICKET_API_KEY"
SOURCE_ENV = "CRICKET_SOURCE"
REFRESH_SECONDS_ENV = "CRICKET_REFRESH_SECONDS"
CACHE_SECONDS_ENV = "CRICKET_CACHE_SECONDS"
SCRAPE_URL_ENV = "CRICKET_SCRAPE_URL"
SCRAPE_MATCH_SELECTOR_ENV = "CRICKET_SCRAPE_MATCH_SELECTOR"
SCRAPE_TEAM_ONE_SELECTOR_ENV = "CRICKET_SCRAPE_TEAM_ONE_SELECTOR"
SCRAPE_TEAM_TWO_SELECTOR_ENV = "CRICKET_SCRAPE_TEAM_TWO_SELECTOR"
SCRAPE_SCORE_SELECTOR_ENV = "CRICKET_SCRAPE_SCORE_SELECTOR"
SCRAPE_STATUS_SELECTOR_ENV = "CRICKET_SCRAPE_STATUS_SELECTOR"
DEFAULT_REFRESH_SECONDS = 60
DEFAULT_SCORE_CACHE_SECONDS = 60
DEFAULT_SCHEDULE_CACHE_SECONDS = 300
DEFAULT_SCRAPE_CACHE_SECONDS = 10
IDLE_SLEEP_SECONDS = 0.05
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "cricket-dude/1.1 (+https://github.com/YashasVM/cricket-dude)"

console = Console()


@dataclass(frozen=True)
class Match:
    description: str
    score: str
    status: str
    is_live: bool = False
    team_one: str = "T1"
    team_two: str = "T2"
    team_one_score: str = ""
    team_two_score: str = ""
    series: str = ""
    match_state: str = ""


@dataclass(frozen=True)
class CacheEntry:
    created_at: float
    data: dict[str, Any]


class ScoreProvider(Protocol):
    def get_matches(self, mode: str = "live", force_refresh: bool = False) -> list[Match]:
        ...


class CricketDataAPI:
    """Small client for CricketData.org / CricAPI score endpoints."""

    def __init__(self, api_key: str, session: requests.Session | None = None, score_cache_seconds: int = DEFAULT_SCORE_CACHE_SECONDS) -> None:
        self.api_key = api_key
        self.base_url = "https://api.cricapi.com/v1"
        self.session = session or requests.Session()
        _set_user_agent(self.session)
        self.score_cache_seconds = score_cache_seconds
        self._cache: dict[tuple[str, tuple[tuple[str, Any], ...]], CacheEntry] = {}

    def get_matches(self, mode: str = "live", force_refresh: bool = False) -> list[Match]:
        if not self.api_key:
            return []

        try:
            if mode in {"live", "recent", "ipl"}:
                return self._get_score_matches(mode, force_refresh=force_refresh)
            return self._get_upcoming_matches(force_refresh=force_refresh)
        except requests.RequestException:
            return []
        except ValueError:
            return []

    def _get_json(self, path: str, cache_seconds: int, force_refresh: bool = False, **params: Any) -> dict[str, Any]:
        cache_key = (path, tuple(sorted(params.items())))
        now = time.monotonic()
        cached = self._cache.get(cache_key)

        if cached and not force_refresh and now - cached.created_at < cache_seconds:
            return cached.data

        response = self.session.get(
            f"{self.base_url}/{path}",
            params={"apikey": self.api_key, **params},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        payload = data if isinstance(data, dict) else {}
        self._cache[cache_key] = CacheEntry(created_at=now, data=payload)
        return payload

    def _get_score_matches(self, mode: str, force_refresh: bool = False) -> list[Match]:
        data = self._get_json("cricScore", cache_seconds=self.score_cache_seconds, force_refresh=force_refresh)
        if data.get("status") != "success":
            return []

        return [
            match
            for match in (self._format_score_match(raw_match) for raw_match in self._iter_dicts(data.get("data", [])))
            if self._matches_mode(raw_match=match, mode=mode)
        ]

    def _get_upcoming_matches(self, force_refresh: bool = False) -> list[Match]:
        data = self._get_json(
            "matches",
            cache_seconds=DEFAULT_SCHEDULE_CACHE_SECONDS,
            force_refresh=force_refresh,
            offset=0,
        )
        if data.get("status") != "success":
            return []

        upcoming = [
            Match(
                description=match.get("name") or "Unknown",
                score=match.get("date") or "TBD",
                status=match.get("status") or "Scheduled",
            )
            for match in self._iter_dicts(data.get("data", []))
            if not match.get("matchStarted", False)
        ]
        return upcoming[:20]

    def _format_score_match(self, match: dict[str, Any]) -> Match:
        team_one = match.get("t1") or "T1"
        team_two = match.get("t2") or "T2"
        team_one_score = match.get("t1s") or ""
        team_two_score = match.get("t2s") or ""
        score = " | ".join(score for score in (team_one_score, team_two_score) if score)

        return Match(
            team_one=team_one,
            team_two=team_two,
            team_one_score=team_one_score,
            team_two_score=team_two_score,
            description=f"{team_one} vs {team_two}",
            score=score or "Not Started",
            status=match.get("status") or "N/A",
            is_live=match.get("ms") == "live",
            series=match.get("series") or "",
            match_state=match.get("ms") or "",
        )

    def _matches_mode(self, raw_match: Match, mode: str) -> bool:
        if mode == "live":
            return raw_match.is_live
        if mode == "recent":
            return raw_match.match_state == "result"
        if mode == "ipl":
            series = raw_match.series.lower()
            return "indian premier league" in series or "ipl" in series or "ipl" in raw_match.description.lower()
        return True

    @staticmethod
    def _iter_dicts(items: Any) -> Iterable[dict[str, Any]]:
        return (item for item in items if isinstance(item, dict))


@dataclass(frozen=True)
class ScrapeSelectors:
    match: str
    score: str
    team_one: str = ""
    team_two: str = ""
    status: str = ""


class ScrapedScoreProvider:
    """Opt-in HTML scoreboard reader for sites the user is allowed to fetch."""

    def __init__(
        self,
        url: str,
        selectors: ScrapeSelectors,
        session: requests.Session | None = None,
        cache_seconds: int = DEFAULT_SCRAPE_CACHE_SECONDS,
    ) -> None:
        self.url = url
        self.selectors = selectors
        self.session = session or requests.Session()
        _set_user_agent(self.session)
        self.cache_seconds = cache_seconds
        self._cache: tuple[float, str] | None = None

    def get_matches(self, mode: str = "live", force_refresh: bool = False) -> list[Match]:
        if mode not in {"live", "ipl"}:
            return []

        try:
            html = self._get_html(force_refresh=force_refresh)
            return self._parse_matches(html)
        except (ImportError, requests.RequestException, ValueError):
            return []

    def _get_html(self, force_refresh: bool = False) -> str:
        now = time.monotonic()
        if self._cache and not force_refresh and now - self._cache[0] < self.cache_seconds:
            return self._cache[1]

        response = self.session.get(self.url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        self._cache = (now, response.text)
        return response.text

    def _parse_matches(self, html: str) -> list[Match]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(self.selectors.match)
        matches = [self._parse_match(card) for card in cards]
        return [match for match in matches if match.score != "N/A"]

    def _parse_match(self, card: Any) -> Match:
        team_one = self._select_text(card, self.selectors.team_one)
        team_two = self._select_text(card, self.selectors.team_two)
        score = self._select_text(card, self.selectors.score) or "N/A"
        status = self._select_text(card, self.selectors.status) or "Live"
        description = f"{team_one} vs {team_two}" if team_one and team_two else self._fallback_description()

        return Match(
            description=description,
            score=score,
            status=status,
            is_live=True,
            team_one=team_one or "T1",
            team_two=team_two or "T2",
            team_one_score=score,
            match_state="live",
            series="scraped",
        )

    def _fallback_description(self) -> str:
        host = urlparse(self.url).netloc or "scoreboard"
        return f"Scraped score from {host}"

    @staticmethod
    def _select_text(card: Any, selector: str) -> str:
        if not selector:
            return ""
        node = card.select_one(selector)
        return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def get_key() -> str | None:
    """Read one key press without blocking the terminal UI."""
    if IS_WINDOWS:
        return _get_windows_key()
    return _get_posix_key()


def _set_user_agent(session: Any) -> None:
    headers = getattr(session, "headers", None)
    if headers is not None:
        headers.update({"User-Agent": USER_AGENT})


def _get_windows_key() -> str | None:
    if not msvcrt.kbhit():
        return None

    char = msvcrt.getch()
    if char in {b"\x00", b"\xe0"}:
        return {b"H": "\x1b[A", b"P": "\x1b[B"}.get(msvcrt.getch())
    if char == b"\r":
        return "\r"
    if char == b"\x1b":
        return "\x1b"

    try:
        return char.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _get_posix_key() -> str | None:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        if not select.select([sys.stdin], [], [], 0.05)[0]:
            return None

        char = sys.stdin.read(1)
        if char == "\x1b" and select.select([sys.stdin], [], [], 0.05)[0]:
            char += sys.stdin.read(2)
        return char
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


class CricketDude:
    def __init__(
        self,
        provider: ScoreProvider,
        refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
    ) -> None:
        self.provider = provider
        self.refresh_seconds = refresh_seconds
        self.menu_options = ["Live Matches", "Recent Results", "Upcoming Schedule", "IPL Special", "Exit"]
        self.selected_idx = 0
        self.current_mode: str | None = None
        self.current_data: list[Match] = []

    def make_scoreboard(self, match: Match) -> Panel:
        header = Text.assemble(
            Text(match.team_one, style="bold cyan"),
            " VS ",
            Text(match.team_two, style="bold magenta"),
        )

        score_grid = Table.grid(expand=True)
        score_grid.add_column(justify="right", ratio=1)
        score_grid.add_column(justify="center", width=5)
        score_grid.add_column(justify="left", ratio=1)
        score_grid.add_row(
            Text(match.team_one_score or "Not Started", style="yellow"),
            "*",
            Text(match.team_two_score or "Not Started", style="yellow"),
        )

        main_layout = Table.grid(padding=1)
        main_layout.add_column(justify="center", ratio=1)
        main_layout.add_row(header)
        main_layout.add_row(score_grid)
        main_layout.add_row(Text(match.status, style="italic green"))
        return Panel(Align.center(main_layout), title="[bold red]LIVE SCOREBOARD[/bold red]", border_style="yellow")

    def generate_menu_layout(self) -> Panel:
        table = Table(box=None, expand=True)
        table.add_column(justify="center")
        table.add_row(
            Panel(
                Text("CRICKET DUDE v1.1", style="bold yellow", justify="center"),
                border_style="green",
            )
        )

        for index, option in enumerate(self.menu_options):
            style = "bold reverse cyan" if index == self.selected_idx else "white"
            table.add_row(Text(f" {option} ", style=style, justify="center"))
        return Panel(table, border_style="dim")

    def generate_viewer_layout(self, mode: str) -> Layout:
        layout = Layout()
        live_matches = [match for match in self.current_data if match.is_live]

        if live_matches and mode in {"live", "ipl"}:
            layout.split_column(
                Layout(name="header", size=3),
                Layout(name="featured", size=9),
                Layout(name="body", ratio=1),
                Layout(name="tail", size=3),
            )
            layout["featured"].update(self.make_scoreboard(live_matches[0]))
        else:
            layout.split_column(Layout(name="header", size=3), Layout(name="body", ratio=1), Layout(name="tail", size=3))

        layout["header"].update(self._make_header(mode))
        layout["body"].update(self._make_match_table())
        layout["tail"].update(Panel(Text("Press R to refresh now | Q or Esc to return", justify="center", style="dim")))
        return layout

    def _make_header(self, mode: str) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            Text(f"Mode: {mode.upper()}", style="bold green"),
            Text(datetime.now().strftime("%H:%M:%S"), style="dim"),
        )
        return Panel(grid, border_style="blue")

    def _make_match_table(self) -> Table:
        table = Table(expand=True, box=box.SIMPLE_HEAD)
        table.add_column("Match", style="cyan", ratio=2)
        table.add_column("Score", style="yellow", ratio=2)
        table.add_column("Status", style="green", ratio=2)

        if not self.current_data:
            table.add_row("No matches found", "-", "Check your API key or try again later")
            return table

        for match in self.current_data:
            table.add_row(match.description, match.score, match.status)
        return table

    def start(self) -> None:
        while True:
            if self.current_mode is None:
                if not self._show_menu():
                    return
            else:
                self._show_matches()

    def _show_menu(self) -> bool:
        with Live(self.generate_menu_layout(), screen=True) as live:
            while self.current_mode is None:
                live.update(self.generate_menu_layout())
                key = get_key()

                if key is None:
                    time.sleep(IDLE_SLEEP_SECONDS)
                elif key == "\x1b[A":
                    self.selected_idx = (self.selected_idx - 1) % len(self.menu_options)
                elif key == "\x1b[B":
                    self.selected_idx = (self.selected_idx + 1) % len(self.menu_options)
                elif key in {"\r", " "}:
                    if not self._select_menu_option():
                        return False
                elif key == "\x1b":
                    return False
        return True

    def _select_menu_option(self) -> bool:
        choice = self.menu_options[self.selected_idx]
        if choice == "Exit":
            return False

        self.current_mode = choice.split()[0].lower()
        return True

    def _show_matches(self) -> None:
        self.current_data = self.provider.get_matches(self.current_mode or "live")
        last_update = time.monotonic()

        with Live(self.generate_viewer_layout(self.current_mode or "live"), screen=True) as live:
            while self.current_mode:
                if time.monotonic() - last_update > self.refresh_seconds:
                    self.current_data = self.provider.get_matches(self.current_mode)
                    last_update = time.monotonic()

                live.update(self.generate_viewer_layout(self.current_mode))
                key = get_key()
                if key is None:
                    time.sleep(IDLE_SLEEP_SECONDS)
                elif key in {"r", "R"}:
                    self.current_data = self.provider.get_matches(self.current_mode, force_refresh=True)
                    last_update = time.monotonic()
                elif key in {"\x1b", "q", "Q"}:
                    self.current_mode = None


def _get_positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _build_provider(cache_seconds: int) -> ScoreProvider | None:
    source = os.environ.get(SOURCE_ENV, "api").strip().lower()
    if source == "scrape":
        return _build_scrape_provider()
    if source != "api":
        console.print(f"[bold red]Unknown {SOURCE_ENV}: {source}[/bold red]")
        return None

    api_key = os.environ.get(API_KEY_ENV, "")
    if not api_key:
        console.print(f"[bold red]Missing {API_KEY_ENV}.[/bold red] Set it before running cricket-dude.")
        return None
    return CricketDataAPI(api_key, score_cache_seconds=cache_seconds)


def _build_scrape_provider() -> ScoreProvider | None:
    url = os.environ.get(SCRAPE_URL_ENV, "").strip()
    match_selector = os.environ.get(SCRAPE_MATCH_SELECTOR_ENV, "").strip()
    score_selector = os.environ.get(SCRAPE_SCORE_SELECTOR_ENV, "").strip()

    if not url or not match_selector or not score_selector:
        console.print(
            "[bold red]Scrape mode needs CRICKET_SCRAPE_URL, "
            "CRICKET_SCRAPE_MATCH_SELECTOR, and CRICKET_SCRAPE_SCORE_SELECTOR.[/bold red]"
        )
        return None

    selectors = ScrapeSelectors(
        match=match_selector,
        score=score_selector,
        team_one=os.environ.get(SCRAPE_TEAM_ONE_SELECTOR_ENV, "").strip(),
        team_two=os.environ.get(SCRAPE_TEAM_TWO_SELECTOR_ENV, "").strip(),
        status=os.environ.get(SCRAPE_STATUS_SELECTOR_ENV, "").strip(),
    )
    cache_seconds = _get_positive_int_env(CACHE_SECONDS_ENV, DEFAULT_SCRAPE_CACHE_SECONDS)
    return ScrapedScoreProvider(url=url, selectors=selectors, cache_seconds=cache_seconds)


def main() -> None:
    refresh_seconds = _get_positive_int_env(REFRESH_SECONDS_ENV, DEFAULT_REFRESH_SECONDS)
    cache_seconds = _get_positive_int_env(CACHE_SECONDS_ENV, DEFAULT_SCORE_CACHE_SECONDS)
    provider = _build_provider(cache_seconds)
    if provider is None:
        return

    try:
        CricketDude(provider, refresh_seconds=refresh_seconds).start()
    except KeyboardInterrupt:
        pass
    finally:
        console.print("[bold red]Cleaning up the pitch... Goodbye![/bold red]")


if __name__ == "__main__":
    main()
