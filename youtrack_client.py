import logging
import requests
from dataclasses import dataclass
import os

token = os.environ.get('YOUTRACK_TOKEN')
base_url = os.environ.get('YOUTRACK_BASE_URL', 'https://eutima.youtrack.cloud')

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger('YouTrackClient')
logger.setLevel(logging.WARNING)


@dataclass
class Issue:
    id: str
    idReadable: str
    summary: str
    project_name: str


@dataclass
class IssueWorkItem:
    id: str


@dataclass
class Project:
    id: str
    shortName: str
    name: str


class YouTrackClient():

    def __init__(self, token=token):
        self.headers = {
            'Authorization': f'Bearer {token}'
        }

    def fetch_projects(self) -> list[Project]:
        response = requests.get(
            f'{base_url}/api/admin/projects?fields=id,shortName,name',
            headers=self.headers
        )
        if response.status_code == 200:
            logger.debug('fetched %s Projects', len(response.json()))
            return [
                Project(
                    id=p['id'],
                    shortName=p['shortName'],
                    name=p['name'],
                ) for p in response.json()
            ]
        logger.error('failed to fetch Projects: %s', response.text)
        return None

    def create_issue(self, project_id: str, summary: str, description: str) -> None:
        response = requests.post(
            f'{base_url}/api/issues',
            json={
                'project': {'id': project_id},
                'summary': summary,
                'description': description
            },
            headers=self.headers
        )
        if response.status_code == 200:
            logger.debug('Issue Created: %s', response.text)
            return
        logger.error('failed to create an Issue: %s', response.text)

    def fetch_issues(self) -> list[Issue]:
        response = requests.get(
            f'{base_url}/api/issues?fields=id,idReadable,project(name),summary&query=State:%20{{In Progress}} | State:%20{{Open}} State:%20{{Planned}} ',
            headers=self.headers
        )
        if response.status_code == 200:
            logger.debug('fetched %s Issues', len(response.json()))
            return [
                Issue(
                    id=i['id'],
                    idReadable=i['idReadable'],
                    summary=i['summary'],
                    project_name=i['project']['name']
                ) for i in response.json()
            ]
        logger.error('failed to fetch Issues: %s', response.text)
        return None

    def add_work_log(self, issue: Issue, text: str, duration_minutes: int) -> IssueWorkItem:
        response = requests.post(
            f'{base_url}/api/issues/{issue.id}/timeTracking/workItems?fields=id,idReadable',
            json={
                'text': text,
                'duration': {
                    'minutes': duration_minutes
                }
            },
            headers=self.headers
        )
        if response.status_code == 200:
            logger.debug('created an Issue WorkItem: %s', response.text)
            return IssueWorkItem(
                id=response.json()['id'],
            )
        logger.error('failed to create an Issue WorkItem: %s', response.text)
        return None
