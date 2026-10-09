param([string]$Repo=".")
python "$PSScriptRoot\studio.py" --repo $Repo --no-open
