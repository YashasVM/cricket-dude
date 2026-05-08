🏏 Cricket Dude (Ultimate TUI Edition)

Cricket Dude is a high-performance Terminal User Interface (TUI) for die-hard cricket fans who spend their time in the command line. Why open a browser when you can track live ball-by-ball status directly in your terminal with zero latency?

🧐 What is this for?

Most sports websites are heavy, filled with ads, and slow. Cricket Dude solves this by:

Providing a lightweight alternative to websites.

Offering a Live Scoreboard that refreshes every 15 seconds.

Categorizing matches into Live, Recent Results, and Upcoming Schedules.

Including an IPL Special mode for the T20 season.

🚀 How to Run

Option 1: Standard Installation (Recommended)

This installs the app globally on your system so you can run it from anywhere.

git clone [https://github.com/mrduhlol/cricket-dude.git](https://github.com/mrduhlol/cricket-dude.git)
cd cricket-dude
pip install .
cricket-dude


Option 2: Run directly via Python

If you don't want to install it globally:

pip install rich requests
python main.py


📊 Project Vitals

Metric

Status

Current Version

v1.0.0 (Stable)

Total Downloads



Repository Views



Stars



⌨️ Controls & Navigation

[↑ / ↓] Arrows: Cycle through menu options.

[Enter / Space]: Confirm selection and enter match view.

[Q / Esc]: Go back to the main menu or exit the application.

[Ctrl + C]: Emergency kill (Force close).

🛠 Advanced Configuration

The app comes with a built-in "community" API key. However, for high-frequency usage, it is recommended to get your own key from CricketData.org.

Set your custom key in your environment variables:

Windows: $env:CRICKET_API_KEY="your-key-here"

Linux/macOS: export CRICKET_API_KEY="your-key-here"

📦 What's Inside?

main.py: The engine. Handles API requests and the Rich UI rendering.

setup.py: Allows you to install the tool as a system command.

.gitignore: Keeps your GitHub repo clean of Python cache files.

📄 License

Distributed under the MIT License. You are free to use, modify, and distribute this software.

Developed by mrduhlol. Give it a ⭐ if you like it!