"""Generate launchd jobs for the unattended capture run (macOS, zero-cost).

Three independent agents so no single failure is silent:
  * capture tick  — every 5 min, self-throttling (mlfootball.market.schedule)
  * watchdog      — every 30 min, dead-man alert (mlfootball.market.watchdog)
  * integrity     — daily 09:00 local (mlfootball.market.integrity)

Run ``python -m mlfootball.market.deploy`` to write the three .plist files into
``mlfootball/market/deploy/`` with absolute paths baked in, then follow the printed
``launchctl`` lines to load them. Logs land in ``data/logs/``.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VENV_PY = REPO / ".venv" / "bin" / "python"
OUT = Path(__file__).resolve().parent / "deploy"
LOGS = REPO / "data" / "logs"
LABEL = "dev.williamcatt.mvm"

JOBS = {
    "tick":      {"args": ["-m", "mlfootball.market.schedule"], "interval": 300},
    "watchdog":  {"args": ["-m", "mlfootball.market.watchdog"], "interval": 1800},
    "integrity": {"args": ["-m", "mlfootball.market.integrity"], "calendar": (9, 0)},
}

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{py}</string>{args}
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONPATH</key><string>{repo}</string></dict>
  <key>WorkingDirectory</key><string>{repo}</string>
  {trigger}
  <key>StandardOutPath</key><string>{logs}/{name}.out.log</string>
  <key>StandardErrorPath</key><string>{logs}/{name}.err.log</string>
</dict>
</plist>
"""


def _args_xml(args):
    return "".join(f"\n    <string>{a}</string>" for a in args)


def _trigger(job):
    if "interval" in job:
        return f"<key>StartInterval</key><integer>{job['interval']}</integer>"
    h, m = job["calendar"]
    return ("<key>StartCalendarInterval</key>\n  <dict>"
            f"<key>Hour</key><integer>{h}</integer>"
            f"<key>Minute</key><integer>{m}</integer></dict>")


def generate() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    written = []
    for name, job in JOBS.items():
        label = f"{LABEL}.{name}"
        text = PLIST.format(
            label=label, py=VENV_PY, args=_args_xml(job["args"]), repo=REPO,
            trigger=_trigger(job), logs=LOGS, name=name)
        path = OUT / f"{label}.plist"
        path.write_text(text)
        written.append(path)
    return written


if __name__ == "__main__":
    paths = generate()
    print("Wrote launchd jobs:")
    for p in paths:
        print(f"  {p}")
    print("\nLoad them (capture starts immediately, survives logout/sleep-wake):")
    for p in paths:
        print(f"  cp '{p}' ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/{p.name}")
    print("\nFor off-machine dead-man email, export before loading (Gmail app password):")
    print("  launchctl setenv MVM_SMTP_USER you@gmail.com")
    print("  launchctl setenv MVM_SMTP_PASS 'app-password'")
    print("\nUnload:  launchctl unload ~/Library/LaunchAgents/<label>.plist", file=sys.stderr)
