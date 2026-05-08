from __future__ import annotations

import os
import sys
import time
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Protocol

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


REFRESH_SECONDS_ENV = "CRICKET_REFRESH_SECONDS"
CACHE_SECONDS_ENV = "CRICKET_CACHE_SECONDS"
DEFAULT_REFRESH_SECONDS = 5
DEFAULT_CRICBUZZ_CACHE_SECONDS = 5
IDLE_SLEEP_SECONDS = 0.05
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "cricket-dude/1.4 (+https://github.com/YashasVM/cricket-dude)"
CRICBUZZ_LIVE_SCORES_URL = "https://www.cricbuzz.com/cricket-match/live-scores"

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


class ScoreProvider(Protocol):
    def get_matches(self, mode: str = "live", force_refresh: bool = False) -> list[Match]:
        ...


class CricbuzzLiveProvider:
    """Built-in score source that works without user-provided keys or URLs."""

    def __init__(
        self,
        session: requests.Session | None = None,
        cache_seconds: int = DEFAULT_CRICBUZZ_CACHE_SECONDS,
    ) -> None:
        self.session = session or requests.Session()
        _set_user_agent(self.session)
        self.cache_seconds = cache_seconds
        self._cache: tuple[float, list[Match]] | None = None

    def get_matches(self, mode: str = "live", force_refresh: bool = False) -> list[Match]:
        try:
            matches = self._get_all_matches(force_refresh=force_refresh)
        except (requests.RequestException, ValueError, json.JSONDecodeError):
            return []

        if mode == "live":
            return [match for match in matches if match.is_live]
        if mode == "recent":
            return [match for match in matches if match.match_state.lower() == "complete"]
        if mode == "ipl":
            return [
                match
                for match in matches
                if "indian premier league" in match.series.lower() or "ipl" in match.series.lower()
            ]
        return [match for match in matches if match.match_state.lower() in {"preview", "upcoming"}]

    def _get_all_matches(self, force_refresh: bool = False) -> list[Match]:
        now = time.monotonic()
        if self._cache and not force_refresh and now - self._cache[0] < self.cache_seconds:
            return self._cache[1]

        response = self.session.get(
            CRICBUZZ_LIVE_SCORES_URL,
            params={"_": int(time.time() * 1000)},
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        matches = self._parse_matches(response.text)
        self._cache = (now, matches)
        return matches

    def _parse_matches(self, html: str) -> list[Match]:
        text = html.replace('\\"', '"').replace("\\/", "/").replace("\\n", "\n")
        marker = '"matchesList":{"matches":'
        marker_index = text.find(marker)
        if marker_index == -1:
            return []

        start = marker_index + len(marker)
        end = self._find_balanced_end(text, start, "[", "]")
        raw_matches = json.loads(text[start:end])

        return [
            match
            for match in (self._format_match(raw_match) for raw_match in self._iter_match_dicts(raw_matches))
            if match is not None
        ]

    def _format_match(self, raw_match: dict[str, Any]) -> Match | None:
        match = raw_match.get("match", {})
        info = match.get("matchInfo", {})
        if not isinstance(match, dict) or not isinstance(info, dict):
            return None

        team_one = self._team_name(info.get("team1"))
        team_two = self._team_name(info.get("team2"))
        team_one_score = self._team_score(match.get("matchScore", {}).get("team1Score", {}))
        team_two_score = self._team_score(match.get("matchScore", {}).get("team2Score", {}))
        score = " | ".join(score for score in (team_one_score, team_two_score) if score)
        state = str(info.get("state") or info.get("stateTitle") or "")
        status = str(info.get("status") or info.get("shortStatus") or state or "Scheduled")
        series = str(info.get("seriesName") or "")
        match_desc = str(info.get("matchDesc") or "").strip()
        description_parts = [f"{team_one} vs {team_two}"]
        if match_desc:
            description_parts.append(match_desc)

        return Match(
            description=" - ".join(description_parts),
            score=score or self._start_time(info) or "Not Started",
            status=status,
            is_live=self._is_live_state(state),
            team_one=team_one,
            team_two=team_two,
            team_one_score=team_one_score,
            team_two_score=team_two_score,
            series=series,
            match_state=state,
        )

    @staticmethod
    def _find_balanced_end(text: str, start: int, opener: str, closer: str) -> int:
        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    return index + 1

        raise ValueError("Could not find complete match list in Cricbuzz response.")

    @staticmethod
    def _iter_match_dicts(items: Any) -> Iterable[dict[str, Any]]:
        return (item for item in items if isinstance(item, dict))

    @staticmethod
    def _team_name(team: Any) -> str:
        if not isinstance(team, dict):
            return "TBD"
        return str(team.get("teamSName") or team.get("teamName") or "TBD")

    @staticmethod
    def _team_score(score: Any) -> str:
        if not isinstance(score, dict):
            return ""

        innings = [
            innings_data
            for innings_data in score.values()
            if isinstance(innings_data, dict) and "runs" in innings_data
        ]
        innings.sort(key=lambda item: int(item.get("inningsId") or 0))
        return " & ".join(CricbuzzLiveProvider._innings_score(innings_data) for innings_data in innings)

    @staticmethod
    def _innings_score(innings: dict[str, Any]) -> str:
        runs = innings.get("runs", 0)
        wickets = innings.get("wickets", 0)
        overs = innings.get("overs")
        score = f"{runs}/{wickets}"
        return f"{score} ({overs} ov)" if overs is not None else score

    @staticmethod
    def _is_live_state(state: str) -> bool:
        state_lower = state.lower()
        return bool(state_lower) and state_lower not in {"preview", "complete", "upcoming"}

    @staticmethod
    def _start_time(info: dict[str, Any]) -> str:
        start_date = info.get("startDate")
        if not start_date:
            return ""
        try:
            return datetime.fromtimestamp(int(start_date) / 1000).strftime("%d %b, %H:%M")
        except (TypeError, ValueError, OSError):
            return ""


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
            Text(self._display_team_score(match.team_one_score), style="yellow"),
            "*",
            Text(self._display_team_score(match.team_two_score), style="yellow"),
        )

        main_layout = Table.grid(padding=1)
        main_layout.add_column(justify="center", ratio=1)
        main_layout.add_row(header)
        main_layout.add_row(score_grid)
        if match.series:
            main_layout.add_row(Text(match.series, style="dim"))
        main_layout.add_row(Text(match.status, style="italic green"))
        return Panel(Align.center(main_layout), title="[bold red]LIVE SCOREBOARD[/bold red]", border_style="yellow")

    def generate_menu_layout(self) -> Panel:
        table = Table(box=None, expand=True)
        table.add_column(justify="center")
        table.add_row(
            Panel(
                Text("CRICKET DUDE v1.4", style="bold yellow", justify="center"),
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
        table.add_column("Match", style="cyan", ratio=3, overflow="fold")
        table.add_column("Team 1", style="yellow", ratio=2, overflow="fold")
        table.add_column("Team 2", style="yellow", ratio=2, overflow="fold")
        table.add_column("Status", style="green", ratio=3, overflow="fold")

        if not self.current_data:
            table.add_row("No matches found", "-", "-", "Try refreshing in a moment")
            return table

        for match in self.current_data:
            table.add_row(
                self._match_label(match),
                self._team_score_cell(match.team_one, match.team_one_score),
                self._team_score_cell(match.team_two, match.team_two_score),
                self._status_cell(match),
            )
        return table

    @staticmethod
    def _display_team_score(score: str) -> str:
        return score or "Yet to bat"

    @staticmethod
    def _team_score_cell(team: str, score: str) -> Text:
        cell = Text()
        cell.append(team, style="bold")
        cell.append("\n")
        cell.append(CricketDude._compact_score(score), style="yellow")
        return cell

    @staticmethod
    def _compact_score(score: str) -> str:
        if not score:
            return "Yet to bat"
        return score.replace(" (", " ").replace(" ov)", "ov")

    @staticmethod
    def _match_label(match: Match) -> Text:
        label = Text()
        label.append(match.description, style="bold cyan")
        if match.series:
            label.append("\n")
            label.append(match.series, style="dim")
        return label

    @staticmethod
    def _status_cell(match: Match) -> Text:
        status = Text(match.status or "Scheduled", style="green")
        if match.match_state:
            status.append("\n")
            status.append(match.match_state, style="dim")
        return status

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
        self.current_data = self.provider.get_matches(self.current_mode or "live", force_refresh=True)
        last_update = time.monotonic()
        last_render_second = -1

        with Live(self.generate_viewer_layout(self.current_mode or "live"), screen=True) as live:
            while self.current_mode:
                should_render = False
                if time.monotonic() - last_update > self.refresh_seconds:
                    self.current_data = self.provider.get_matches(self.current_mode, force_refresh=True)
                    last_update = time.monotonic()
                    should_render = True

                current_second = datetime.now().second
                if current_second != last_render_second:
                    last_render_second = current_second
                    should_render = True

                if should_render:
                    live.update(self.generate_viewer_layout(self.current_mode))

                key = get_key()
                if key is None:
                    time.sleep(IDLE_SLEEP_SECONDS)
                elif key in {"r", "R"}:
                    self.current_data = self.provider.get_matches(self.current_mode, force_refresh=True)
                    last_update = time.monotonic()
                    live.update(self.generate_viewer_layout(self.current_mode))
                elif key in {"\x1b", "q", "Q"}:
                    self.current_mode = None


def _get_positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _build_provider(cache_seconds: int) -> ScoreProvider:
    return CricbuzzLiveProvider(cache_seconds=cache_seconds)


def main() -> None:
    refresh_seconds = _get_positive_int_env(REFRESH_SECONDS_ENV, DEFAULT_REFRESH_SECONDS)
    cache_seconds = _get_positive_int_env(CACHE_SECONDS_ENV, DEFAULT_CRICBUZZ_CACHE_SECONDS)
    provider = _build_provider(cache_seconds)

    try:
        CricketDude(provider, refresh_seconds=refresh_seconds).start()
    except KeyboardInterrupt:
        pass
    finally:
        console.print("[bold red]Cleaning up the pitch... Goodbye![/bold red]")


if __name__ == "__main__":
    main()
