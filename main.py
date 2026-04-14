#!/bin/env python3

import time
import datetime
import re
import select
import subprocess
import sys
import tempfile
import termios
import tty
from enum import Enum
import argparse
import os
import math

import questionary
from questionary import Style as QStyle
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel

from youtrack_client import YouTrackClient, Issue, base_url
from thefuzz import process
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn

SELECT_STYLE = QStyle([
    ('pointer',     'fg:cyan bold'),
    ('highlighted', 'fg:cyan'),
    ('selected',    'fg:green bold'),
    ('answer',      'fg:green bold'),
    ('question',    'bold'),
])

console = Console()

_gemini_work_log = Agent(
    GoogleModel('gemini-2.5-flash-lite'),
    system_prompt=(
        "Fix spelling and grammar in the given text. "
        "adapt it so a non tecnical person understand."
        "You are generating a worklog entry for an issue. "
        "Return only the corrected text, no explanations."
    ),
)
_gemini_issue_title = Agent(
    GoogleModel('gemini-2.5-flash-lite'),
    system_prompt=(
        "Fix spelling and grammar in the given text. "
        "The target audience are software developers. "
        "You are generating a title for an issue. "
        "Return only the corrected text, no explanations."
    ),
)
_gemini_issue_description = Agent(
    GoogleModel('gemini-2.5-flash-lite'),
    system_prompt=(
        "Fix spelling and grammar in the given text and "
        "The target audience are software developers which have to implement this issue "
        "Return only the corrected text, no explanations."
    ),
)


def fix_text(text: str, agent: Agent) -> str:
    if not text:
        return text
    result = agent.run_sync(text)
    return result.output


def try_fix_text(text: str, agent: Agent) -> str:
    try:
        return fetch_with_spinner(lambda: fix_text(text, agent), "Fixing grammar...")
    except Exception as e:
        console.print(
            f"[yellow]Grammar fix failed ({e}), using original text[/yellow]")
        return text


work_log_file = '/home/royman/worklog/worklog'
search_result_limit = 10


class WorkAction(Enum):
    WORK_IN_PROGRESS = 'WORK_IN_PROGRESS'
    SHOW_WORK_LOG = 'SHOW_WORK_LOG'
    CLEAR_WORK_LOG = 'CLEAR_WORK_LOG'
    CREATE_ISSUE = 'CREATE_ISSUE'


def fetch_with_spinner(fn, message):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task(description=message, total=None)
        return fn()


def format_time(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02}:{m:02}:{s:02}"
    return f"{m:02}:{s:02}"


def _timer_display(seconds: int, paused: bool) -> Text:
    icon = "⏸" if paused else "▶"
    hint = "Space to resume · Ctrl+C to stop" if paused else "Space to pause · Ctrl+C to stop"
    style = "bold yellow" if paused else "bold green"
    t = Text()
    t.append(f"{icon}  {format_time(seconds)}", style=style)
    t.append(f"  {hint}", style="dim")
    return t


def run_timer() -> int:
    """Interactive timer with pause. Space = pause/resume, Ctrl+C = stop. Returns elapsed seconds."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    elapsed = 0.0
    paused = False

    try:
        tty.setcbreak(fd)
        last_tick = time.monotonic()

        with Live(console=console, refresh_per_second=4) as live:
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.25)
                if ready:
                    ch = sys.stdin.read(1)
                    if ch == ' ':
                        paused = not paused

                now = time.monotonic()
                if not paused:
                    elapsed += now - last_tick
                last_tick = now

                live.update(_timer_display(int(elapsed), paused))
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return int(elapsed)


def open_in_editor() -> str:
    """Open $EDITOR (default: vim) for description. Returns stripped file contents."""
    editor = os.environ.get('EDITOR', 'vim')
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        tmp_path = f.name
    try:
        subprocess.run([editor, tmp_path], check=False)
        with open(tmp_path, 'r') as f:
            return f.read().strip()
    finally:
        os.unlink(tmp_path)


def create_issue():
    choices = fetch_with_spinner(
        YouTrackClient().fetch_projects, "Fetching projects...")
    if not choices:
        console.print("[red]Failed to fetch projects[/red]")
        return None

    query = Prompt.ask("[cyan]Search project[/cyan]")
    results = process.extract(query, choices, limit=search_result_limit)

    project = questionary.select(
        "Select project:",
        choices=[
            questionary.Choice(title=f"{m.shortName}  {m.name}", value=m)
            for m, _ in results
        ],
        style=SELECT_STYLE,
    ).ask()
    if project is None:
        return None

    title = Prompt.ask("[cyan]Title[/cyan]")
    title = try_fix_text(title, _gemini_issue_title)
    description = open_in_editor()
    description = try_fix_text(description, _gemini_issue_description)

    id, idReadable = YouTrackClient().create_issue(
        project_id=project.id,
        summary=title,
        description=description,
    )
    if idReadable is None:
        console.print("[red]Failed to create issue in YouTrack[/red]")
    else:
        console.print(f"[green]Issue created in {project.shortName}[/green]")
        console.print(Panel(
            f"{title}\n[dim]{description}[/dim]",
            title=f"[green][bold]{idReadable}[/bold] — Issue Created[/green]",
            border_style="green",
        ))

    return id


def work_in_progress():
    choices = fetch_with_spinner(
        YouTrackClient().fetch_issues, "Fetching issues...")
    if not choices:
        console.print("[red]Failed to fetch issues[/red]")
        return

    _NEW = "__new__"

    try:
        while True:
            query = Prompt.ask("[cyan]Search issue[/cyan]")
            results = process.extract(
                query, choices, limit=search_result_limit)

            selected = questionary.select(
                "Select issue:",
                choices=[
                    questionary.Choice(
                        title=f"{m.idReadable}  {m.summary}  [{m.project_name}]",
                        value=m,
                    )
                    for m, _ in results
                ] + [questionary.Choice(title="[+] Create new issue", value=_NEW)],
                style=SELECT_STYLE,
            ).ask()

            if selected is None:
                raise KeyboardInterrupt
            if selected == _NEW:
                create_issue()
                choices = fetch_with_spinner(
                    YouTrackClient().fetch_issues, "Refreshing issues...")
                continue

            ticket: Issue = selected
            console.print(Panel(
                f"[bold]{ticket.idReadable}[/bold] — {ticket.summary}\n[dim]{ticket.project_name}[/dim]",
                title="[green]Working on[/green]",
                border_style="green",
            ))
            console.print("[dim]Space to pause · Ctrl+C to stop[/dim]\n")

            time_spent_seconds = run_timer()

            console.print(
                f"[green]Stopped at {format_time(time_spent_seconds)}[/green]")
            description = open_in_editor()
            description = try_fix_text(description, _gemini_work_log)

            duration_minutes = 5 * \
                round(math.ceil(time_spent_seconds / 60) / 5)
            duration_minutes = max(duration_minutes, 5)

            default_duration_str = (
                f"{duration_minutes // 60}h {duration_minutes % 60}m"
                if duration_minutes >= 60
                else f"{duration_minutes}m"
            )
            while True:
                duration_input = Prompt.ask(
                    "[cyan]Duration[/cyan]", default=default_duration_str)
                match = re.fullmatch(
                    r'\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*', duration_input, re.IGNORECASE)
                if match and (match.group(1) or match.group(2)):
                    h = int(match.group(1) or 0)
                    m = int(match.group(2) or 0)
                    duration_minutes = max(h * 60 + m, 1)
                    break
                console.print(
                    "[red]Invalid duration. Use format like: 2h 5m, 1h, 30m[/red]")

            summary_text = (
                f"[bold]Issue:[/bold]    {ticket.idReadable} — {ticket.summary}\n"
                f"[bold]Duration:[/bold] {duration_minutes} minutes\n"
                f"[bold]Note:[/bold]     {description or '[dim](none)[/dim]'}"
            )
            console.print(Panel(
                summary_text, title="[yellow]Work log summary[/yellow]", border_style="yellow"))

            if not Confirm.ask("[cyan]Submit to YouTrack?[/cyan]", default=True):
                console.print("[yellow]Skipped submission[/yellow]")
                continue

            separator = '-' * 40
            with open(work_log_file, 'a') as f:
                f.write(datetime.datetime.now().isoformat() + '\n')
                f.write(f'{ticket.idReadable} - {ticket.summary}\n')
                f.write(f'{format_time(time_spent_seconds)}\n')
                if description:
                    f.write(description + '\n')
                f.write(f'{separator}\n')

            response = YouTrackClient().add_work_log(
                issue=ticket,
                duration_minutes=duration_minutes,
                text=description,
            )
            if response is None:
                console.print("[red]Failed to save in YouTrack[/red]")
            else:
                console.print(
                    f"[green]Logged {duration_minutes}m →[/green] {base_url}/issue/{ticket.idReadable}"
                )

    except KeyboardInterrupt:
        console.print("\n[dim]Bye[/dim]")


def show_work_log():
    if not os.path.exists(work_log_file):
        console.print("[yellow]No worklog found[/yellow]")
        return

    with open(work_log_file, 'r') as f:
        content = f.read()

    entries = [e.strip() for e in re.split(r'\n-+\n?', content) if e.strip()]
    if not entries:
        console.print("[yellow]Worklog is empty[/yellow]")
        return

    for entry in reversed(entries):
        lines = entry.strip().splitlines()
        if len(lines) < 3:
            continue
        timestamp, issue_line, duration = lines[0], lines[1], lines[2]
        notes = '\n'.join(lines[3:]).strip()

        panel_content = f"[bold cyan]{issue_line}[/bold cyan]  [green]{duration}[/green]"
        if notes:
            panel_content += f"\n[dim]{notes}[/dim]"
        console.print(
            Panel(panel_content, title=f"[dim]{timestamp}[/dim]", border_style="dim"))


def clear_work_log():
    if os.path.exists(work_log_file):
        archived = f'{work_log_file}-{datetime.datetime.now().isoformat()}'
        os.rename(work_log_file, archived)
        console.print(f"[green]Worklog archived →[/green] {archived}")
    else:
        console.print("[yellow]No worklog to clear[/yellow]")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="YouTrack work time tracker")
    parser.add_argument(
        '-a', '--action',
        required=True, choices=[v.value for v in WorkAction],
    )

    os.makedirs(os.path.dirname(work_log_file), exist_ok=True)

    args = parser.parse_args()
    match args.action:
        case WorkAction.WORK_IN_PROGRESS.value:
            work_in_progress()
        case WorkAction.SHOW_WORK_LOG.value:
            show_work_log()
        case WorkAction.CLEAR_WORK_LOG.value:
            clear_work_log()
        case WorkAction.CREATE_ISSUE.value:
            create_issue()
