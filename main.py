from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

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
DEFAULT_REFRESH_SECONDS = 15
IDLE_SLEEP_SECONDS = 0.05
REQUEST_TIMEOUT_SECONDS = 10

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


class CricketDataAPI:
    """Small client for CricketData.org / CricAPI score endpoints."""

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self.base_url = "https://api.cricapi.com/v1"
        self.session = session or requests.Session()

    def get_matches(self, mode: str = "live") -> list[Match]:
        if not self.api_key:
            return []

        try:
            if mode in {"live", "recent", "ipl"}:
                return self._get_score_matches(mode)
            return self._get_upcoming_matches()
        except requests.RequestException:
            return []
        except ValueError:
            return []

    def _get_json(self, path: str, **params: Any) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/{path}",
            params={"apikey": self.api_key, **params},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _get_score_matches(self, mode: str) -> list[Match]:
        data = self._get_json("cricScore")
        if data.get("status") != "success":
            return []

        return [
            match
            for match in (self._format_score_match(raw_match) for raw_match in self._iter_dicts(data.get("data", [])))
            if self._matches_mode(raw_match=match, mode=mode)
        ]

    def _get_upcoming_matches(self) -> list[Match]:
        data = self._get_json("matches", offset=0)
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
            return "indian premier league" in series or "ipl" in raw_match.description.lower()
        return True

    @staticmethod
    def _iter_dicts(items: Any) -> Iterable[dict[str, Any]]:
        return (item for item in items if isinstance(item, dict))


def get_key() -> str | None:
    """Read one key press without blocking the terminal UI."""
    if IS_WINDOWS:
        return _get_windows_key()
    return _get_posix_key()


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
    def __init__(self, api_key: str, refresh_seconds: int = DEFAULT_REFRESH_SECONDS) -> None:
        self.api = CricketDataAPI(api_key)
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
        layout["tail"].update(Panel(Text("Press Q or Esc to return", justify="center", style="dim")))
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
        self.current_data = self.api.get_matches(self.current_mode or "live")
        last_update = time.monotonic()

        with Live(self.generate_viewer_layout(self.current_mode or "live"), screen=True) as live:
            while self.current_mode:
                if time.monotonic() - last_update > self.refresh_seconds:
                    self.current_data = self.api.get_matches(self.current_mode)
                    last_update = time.monotonic()

                live.update(self.generate_viewer_layout(self.current_mode))
                key = get_key()
                if key is None:
                    time.sleep(IDLE_SLEEP_SECONDS)
                elif key in {"\x1b", "q", "Q"}:
                    self.current_mode = None


def main() -> None:
    api_key = os.environ.get(API_KEY_ENV, "")
    if not api_key:
        console.print(f"[bold red]Missing {API_KEY_ENV}.[/bold red] Set it before running cricket-dude.")
        return

    try:
        CricketDude(api_key).start()
    except KeyboardInterrupt:
        pass
    finally:
        console.print("[bold red]Cleaning up the pitch... Goodbye![/bold red]")


if __name__ == "__main__":
    main()
