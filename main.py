#!/bin/env python3

import time
import datetime
from enum import Enum
import argparse
import os
from youtrack_client import YouTrackClient, Issue, base_url
from thefuzz import process
import math


work_log_file = '/tmp/worklog'
refresh_rate_seconds = 5
search_result_limit = 5


class WorkAction(Enum):
    WORK_IN_PROGRESS = 'WORK_IN_PROGRESS'
    SHOW_WORK_LOG = 'SHOW_WORK_LOG'
    CLEAR_WORK_LOG = 'CLEAR_WORK_LOG'
    CREATE_ISSUE = 'CREATE_ISSUE'


def create_issue():
    choices = YouTrackClient().fetch_projects()
    while True:
        query = input('[?] Search Project: ')
        results = process.extract(
            query, choices, limit=search_result_limit)

        for index, (match, score) in enumerate(results):
            print(
                f"[{index}] {match.shortName} - {match.name} (score: {score})")

        choice = input('[?] Choice: ')
        if choice.isnumeric() and 0 <= int(choice) < len(results):
            title = input('[?] Title: ')
            print('[?] Description:')
            description = ['']
            while line := input():
                description.append(line.encode(
                    'utf-8', 'ignore').decode('utf-8', 'ignore'))
            response = YouTrackClient().create_issue(
                project_id=results[int(choice)][0].id,
                summary=title,
                description='\n'.join(description)
            )
            if response is None:
                print('[!] could not save in youtrack')
            return


def work_in_progress():
    choices = YouTrackClient().fetch_issues()
    try:
        while True:
            query = input('[?] Search Issue: ')
            results = process.extract(
                query, choices, limit=search_result_limit)

            for index, (match, score) in enumerate(results):
                print(
                    f"[{index}] {match.idReadable} - {match.summary} (score: {score})")

            choice = input('[?] Choice or "n" to create a new Issue: ')
            if choice.lower().strip() in ['new', 'n']:
                create_issue()
                choices = YouTrackClient().fetch_issues()
            elif choice.isnumeric() and 0 <= int(choice) < len(results):
                ticket: Issue = results[int(choice)][0]
                print(f'{ticket.idReadable} - {ticket.summary}')
                time_spent_seconds = 0
                current_time = '00:00'
                try:
                    while True:
                        print('\r' + current_time, end='', flush=True)
                        time.sleep(refresh_rate_seconds)
                        time_spent_seconds += 5
                        seconds = time_spent_seconds % 60
                        minutes = (time_spent_seconds - seconds) // 60
                        current_time = f'{minutes:>02}:{seconds:>02}'
                except KeyboardInterrupt:
                    print('\n[?] Description:')
                    description = ['']
                    while line := input():
                        description.append(line.encode(
                            'utf-8', 'ignore').decode('utf-8', 'ignore'))
                    separator = '-'*max([len(d_line)
                                        for d_line in description])
                    print(separator)
                    with open(work_log_file, 'a') as f:
                        f.write(datetime.datetime.now().isoformat() + '\n')
                        f.write(f'{ticket.idReadable} - {ticket.summary}\n')
                        f.write(f'{current_time}\n')
                        [f.write(f'{d}\n') for d in description]
                        f.write(f'{separator}\n')
                    duration_minutes = 5 * round(
                        math.ceil(time_spent_seconds / 60) / 5
                    )
                    response = YouTrackClient().add_work_log(
                        issue=ticket,
                        duration_minutes=duration_minutes,
                        text='\n'.join([d for d in description if d])
                    )
                    if response is None:
                        print('[!] could not save in youtrack')
                    else:
                        print(
                            f'{base_url}/issue/{ticket.idReadable}')

    except KeyboardInterrupt:
        print('\nBye 🪼')


def show_work_log():
    if os.path.exists(work_log_file):
        with open(work_log_file, 'r') as f:
            print(f.read())
    else:
        print('No Worklog found')


def clear_work_log():
    if os.path.exists(work_log_file):
        os.rename(
            work_log_file,
            f'{work_log_file}-{datetime.datetime.now().isoformat()}'
        )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-a', '--action',
        required=True, choices=[v.value for v in WorkAction]
    )

    if not os.path.exists(work_log_file):
        os.makedirs(work_log_file)
        os.removedirs(work_log_file)

    args = parser.parse_args()
    match(args.action):
        case WorkAction.WORK_IN_PROGRESS.value:
            work_in_progress()
        case WorkAction.SHOW_WORK_LOG.value:
            show_work_log()
        case WorkAction.CLEAR_WORK_LOG.value:
            clear_work_log()
