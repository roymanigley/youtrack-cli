# Youtrack CLI
> - issue fuzzy search
> - submits the worked time on a issue to youtrack
> - create an issue in youtrack
> - keeps a local worklog for the time tracking

# Featues
- [x] Issue Fuzzy Search
- [x] Issue Time Tracking
- [X] Issue Creation

# Setup `~/.zshrc` or `~/.bashrc`

    chmod +x main.py

    alias worklog='source /home/royman/repo/local/youtrack/.venv/bin/activate && /home/royman/repo/local/youtrack/main.py -a WORK_IN_PROGRESS'
    alias worklog_show='source /home/royman/repo/local/youtrack/.venv/bin/activate && /home/royman/repo/local/youtrack/main.py -a SHOW_WORK_LOG'
    alias worklog_clear='source /home/royman/repo/local/youtrack/.venv/bin/activate && /home/royman/repo/local/youtrack/main.py -a CLEAR_WORK_LOG'
    export YOUTRACK_TOKEN='YOUR_TOKEN'
