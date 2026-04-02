#!/bin/env python3

import time
import datetime
import re
from enum import Enum
import argparse
import os
import math

import questionary
from questionary import Style as QStyle

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



def create_issue():
    choices = fetch_with_spinner(YouTrackClient().fetch_projects, "Fetching projects...")
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
    console.print("[cyan]Description[/cyan] [dim](empty line to finish)[/dim]")
    description_lines = []
    while line := input():
        description_lines.append(line.encode('utf-8', 'ignore').decode('utf-8', 'ignore'))

    response = YouTrackClient().create_issue(
        project_id=project.id,
        summary=title,
        description='\n'.join(description_lines),
    )
    if response is None:
        console.print("[red]Failed to create issue in YouTrack[/red]")
    else:
        console.print(f"[green]Issue created in {project.shortName}[/green]")
    return response


def work_in_progress():
    choices = fetch_with_spinner(YouTrackClient().fetch_issues, "Fetching issues...")
    if not choices:
        console.print("[red]Failed to fetch issues[/red]")
        return

    _NEW = "__new__"

    try:
        while True:
            query = Prompt.ask("[cyan]Search issue[/cyan]")
            results = process.extract(query, choices, limit=search_result_limit)

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
                choices = fetch_with_spinner(YouTrackClient().fetch_issues, "Refreshing issues...")
                continue

            ticket: Issue = selected
            console.print(Panel(
                f"[bold]{ticket.idReadable}[/bold] — {ticket.summary}\n[dim]{ticket.project_name}[/dim]",
                title="[green]Working on[/green]",
                border_style="green",
            ))
            console.print("[dim]Press Ctrl+C to stop the timer[/dim]\n")

            time_spent_seconds = 0
            try:
                with Live(console=console, refresh_per_second=2) as live:
                    while True:
                        live.update(Text(format_time(time_spent_seconds), style="bold green"))
                        time.sleep(1)
                        time_spent_seconds += 1
            except KeyboardInterrupt:
                pass

            console.print(f"\n[green]Stopped at {format_time(time_spent_seconds)}[/green]")
            console.print("[cyan]Description[/cyan] [dim](empty line to finish)[/dim]")
            description_lines = []
            while line := input():
                description_lines.append(line.encode('utf-8', 'ignore').decode('utf-8', 'ignore'))

            duration_minutes = 5 * round(math.ceil(time_spent_seconds / 60) / 5)
            duration_minutes = max(duration_minutes, 5)

            summary_text = (
                f"[bold]Issue:[/bold]    {ticket.idReadable} — {ticket.summary}\n"
                f"[bold]Duration:[/bold] {duration_minutes} minutes\n"
                f"[bold]Note:[/bold]     {' '.join(description_lines) or '[dim](none)[/dim]'}"
            )
            console.print(Panel(summary_text, title="[yellow]Work log summary[/yellow]", border_style="yellow"))

            if not Confirm.ask("[cyan]Submit to YouTrack?[/cyan]", default=True):
                console.print("[yellow]Skipped submission[/yellow]")
                continue

            separator = '-' * 40
            with open(work_log_file, 'a') as f:
                f.write(datetime.datetime.now().isoformat() + '\n')
                f.write(f'{ticket.idReadable} - {ticket.summary}\n')
                f.write(f'{format_time(time_spent_seconds)}\n')
                for d in description_lines:
                    f.write(f'{d}\n')
                f.write(f'{separator}\n')

            response = YouTrackClient().add_work_log(
                issue=ticket,
                duration_minutes=duration_minutes,
                text='\n'.join(description_lines),
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
        console.print(Panel(panel_content, title=f"[dim]{timestamp}[/dim]", border_style="dim"))


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
