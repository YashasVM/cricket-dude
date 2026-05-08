import time
import sys
import os
import requests
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.layout import Layout
from rich import box
from rich.text import Text
from rich.align import Align
from datetime import datetime

try:
    import tty
    import termios
    import select
    IS_WINDOWS = False
except ImportError:
    import msvcrt
    IS_WINDOWS = True

console = Console()

class CricketDataAPI:
    """Official API Client for CricketData.org"""
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.cricapi.com/v1"

    def get_matches(self, mode="live"):
        try:
            if not self.api_key:
                return []

            if mode in ["live", "recent", "ipl"]:
                endpoint = f"{self.base_url}/cricScore?apikey={self.api_key}"
                response = requests.get(endpoint, timeout=10)
                data = response.json()
                
                if data.get("status") != "success": return []

                raw_matches = data.get("data", [])
                formatted_matches = []
                
                for m in raw_matches:
                    match_name = f"{m.get('t1', 'T1')} vs {m.get('t2', 'T2')}"
                    status_text = m.get("status", "N/A")
                    is_match_live = m.get("ms") == "live"
                    
                    if mode == "ipl":
                        series_name = m.get("series", "").lower()
                        if "indian premier league" not in series_name and "ipl" not in match_name.lower():
                            continue
                    else:
                        if mode == "live" and not is_match_live: continue
                        if mode == "recent" and m.get("ms") != "result": continue
                        
                    formatted_matches.append({
                        "t1": m.get('t1', 'T1'), "t2": m.get('t2', 'T2'),
                        "t1s": m.get('t1s', ''), "t2s": m.get('t2s', ''),
                        "mchDesc": match_name,
                        "score": f"{m.get('t1s', '')} | {m.get('t2s', '')}".strip(" |"),
                        "status": status_text, "is_live": is_match_live
                    })
                return formatted_matches
            else:
                endpoint = f"{self.base_url}/matches?apikey={self.api_key}&offset=0"
                response = requests.get(endpoint, timeout=10)
                data = response.json()
                if data.get("status") != "success": return []
                
                upcoming = []
                for m in data.get("data", []):
                    if not m.get("matchStarted", False):
                        upcoming.append({
                            "mchDesc": m.get("name", "Unknown"),
                            "score": m.get("date", "TBD"),
                            "status": m.get("status", "Scheduled"),
                            "is_live": False
                        })
                return upcoming[:20] 
        except Exception:
            return []

def get_key():
    """Universal key reader for terminal navigation."""
    if IS_WINDOWS:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in [b'\x00', b'\xe0']:
                ch2 = msvcrt.getch()
                if ch2 == b'H': return '\x1b[A' # Up
                if ch2 == b'P': return '\x1b[B' # Down
            if ch == b'\r': return '\r'
            if ch == b'\x1b': return '\x1b'
            try: return ch.decode('utf-8')
            except: return None
    else:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch = sys.stdin.read(1)
                if ch == '\x1b':
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        ch += sys.stdin.read(2)
                return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return None

class CricketDude:
    def __init__(self, api_key):
        self.api = CricketDataAPI(api_key)
        self.menu_options = ["Live Matches", "Recent Results", "Upcoming Schedule", "IPL Special", "Exit"]
        self.selected_idx = 0
        self.current_mode = None
        self.current_data = []

    def make_scoreboard(self, match):
        """Generates the main visual scoreboard."""
        t1, t2 = Text(match['t1'], style="bold cyan"), Text(match['t2'], style="bold magenta")
        header = Text.assemble(t1, " VS ", t2)
        score_grid = Table.grid(expand=True)
        score_grid.add_column(justify="right", ratio=1)
        score_grid.add_column(justify="center", width=5)
        score_grid.add_column(justify="left", ratio=1)
        score_grid.add_row(Text(match['t1s'] or "Not Started", style="yellow"), "⚡", Text(match['t2s'] or "Not Started", style="yellow"))
        main_layout = Table.grid(padding=1)
        main_layout.add_column(justify="center", ratio=1)
        main_layout.add_row(header); main_layout.add_row(score_grid); main_layout.add_row(Text(match['status'], style="italic green"))
        return Panel(Align.center(main_layout), title="[bold red]LIVE SCOREBOARD[/bold red]", border_style="yellow")

    def generate_menu_layout(self):
        t = Table(box=None, expand=True); t.add_column(justify="center")
        t.add_row(Panel(Text("🏏 CRICKET DUDE   v1.0", style="bold yellow", justify="center"), border_style="green"))
        for i, opt in enumerate(self.menu_options):
            style = "bold reverse cyan" if i == self.selected_idx else "white"
            t.add_row(Text(f" {opt} ", style=style, justify="center"))
        return Panel(t, border_style="dim")

    def generate_viewer_layout(self, mode):
        layout = Layout()
        live = [m for m in self.current_data if m.get('is_live')]
        if live and mode in ["live", "ipl"]:
            layout.split_column(Layout(name="h", size=3), Layout(name="f", size=9), Layout(name="b", ratio=1), Layout(name="t", size=3))
            layout["f"].update(self.make_scoreboard(live[0]))
        else:
            layout.split_column(Layout(name="h", size=3), Layout(name="b", ratio=1), Layout(name="t", size=3))
        grid = Table.grid(expand=True); grid.add_column(ratio=1); grid.add_column(justify="right")
        grid.add_row(Text(f"🏏 Mode: {mode.upper()}", style="bold green"), Text(datetime.now().strftime("%H:%M:%S"), style="dim"))
        layout["h"].update(Panel(grid, border_style="blue"))
        table = Table(expand=True, box=box.SIMPLE_HEAD)
        table.add_column("Match", style="cyan", ratio=2); table.add_column("Score", style="yellow", ratio=2); table.add_column("Status", style="green", ratio=2)
        for m in self.current_data: table.add_row(m['mchDesc'], m['score'], m['status'])
        layout["b"].update(table)
        layout["t"].update(Panel(Text("Press 'Q' or 'Esc' to return", justify="center", style="dim")))
        return layout

    def start(self):
        while True:
            if self.current_mode is None:
                with Live(self.generate_menu_layout(), screen=True) as live:
                    while self.current_mode is None:
                        live.update(self.generate_menu_layout())
                        k = get_key()
                        if k == '\x1b[A': self.selected_idx = (self.selected_idx - 1) % len(self.menu_options)
                        elif k == '\x1b[B': self.selected_idx = (self.selected_idx + 1) % len(self.menu_options)
                        elif k in ['\r', ' ']:
                            choice = self.menu_options[self.selected_idx]
                            if choice == "Exit": return
                            self.current_mode = choice.split()[0].lower()
                        elif k == '\x1b': return
            else:
                self.current_data = self.api.get_matches(self.current_mode)
                last_upd = time.time()
                with Live(self.generate_viewer_layout(self.current_mode), screen=True) as live:
                    while self.current_mode:
                        if time.time() - last_upd > 15:
                            self.current_data = self.api.get_matches(self.current_mode)
                            last_upd = time.time()
                        live.update(self.generate_viewer_layout(self.current_mode))
                        k = get_key()
                        if k in ['\x1b', 'q', 'Q']: self.current_mode = None

def main():
    # Hidden API key: 489b1347-9764-4ad3-950c-04646b1960fc
    p1, p2, p3, p4, p5 = "489b1347", "9764", "4ad3", "950c", "04646b1960fc"
    default_key = f"{p1}-{p2}-{p3}-{p4}-{p5}"
    key = os.environ.get("CRICKET_API_KEY", default_key)
    try: CricketDude(key).start()
    except KeyboardInterrupt: pass
    console.print("[bold red]Cleaning up the pitch... Goodbye![/bold red]")

if __name__ == "__main__":
    main()