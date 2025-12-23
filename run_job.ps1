# Navigate to the repo folder
Set-Location "$PSScriptRoot"

$logFile = "$PSScriptRoot\job.log"
$date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"$date - Starting job..." | Out-File -Append $logFile

# Pull latest changes from GitHub and log output
git pull origin main 2>&1 | Tee-Object -FilePath $logFile -Append

# Run your custom script and log output
python "$PSScriptRoot\launcher.py" 2>&1 | Tee-Object -FilePath $logFile -Append

# Finish log
$date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"$date - Job finished" | Out-File -Append $logFile