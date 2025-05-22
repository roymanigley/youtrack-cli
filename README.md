# Youtrack CLI
> - issue fuzzy search
> - submits the worked time on a issue to youtrack
> - keeps a local worklog for the time tracking

# Featues
-[x]  Issue Fuzzy Search
-[x]  Issue Time Tracking

# Setup `~/.zshrc` or `~/.bashrc`
    alias worklog='/home/royman/repo/local/youtrack/main.py -a WORK_IN_PROGRESS'
    alias worklog_show='/home/royman/repo/local/youtrack/main.py -a SHOW_WORK_LOG'
    alias worklog_clear='/home/royman/repo/local/youtrack/main.py -a CLEAR_WORK_LOG'
    export YOUTRACK_TOKEN='YOUR_TOKEN'
