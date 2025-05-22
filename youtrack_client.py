import requests
import json
from dataclasses import dataclass
import os

token = os.environ.get('YOUTRACK_TOKEN')
base_url = os.environ.get('YOUTRACK_BASE_URL', 'https://eutima.youtrack.cloud')


@dataclass
class Issue:
    id: str
    idReadable: str
    summary: str
    project_name: str


@dataclass
class IssueWorkItem:
    id: str


class YouTrackClient():

    def __init__(self, token=token):
        self.headers = {
            'Authorization': f'Bearer {token}'
        }

    def fetch_issues(self) -> list[Issue]:
        response = requests.get(
            f'{base_url}/api/issues?fields=id,idReadable,project(name),summary&&query=State:%20{{In Progress}} | State:%20{{Open}} State:%20{{Planned}} ',
            headers=self.headers
        )
        if response.status_code == 200:
            return [
                Issue(
                    id=i['id'],
                    idReadable=i['idReadable'],
                    summary=i['summary'],
                    project_name=i['project']['name']
                ) for i in response.json()
            ]
        print(response.text)
        return None

    def add_work_log(self, issue: Issue, text: str, duration_minutes: int):
        remaining_minutes = duration_minutes % 60
        response = requests.post(
            f'{base_url}/api/issues/{issue.id}/timeTracking/workItems?fields=id,idReadable',
            json={
                'text': text,
                'duration': {
                    'hours': duration_minutes // 60,
                    'minutes': remaining_minutes
                }
            },
            headers=self.headers
        )
        if response.status_code == 200:
            return IssueWorkItem(
                id=response.json()['id'],
            )
        print(response.status_code, response.text)
        return None
