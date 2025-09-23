# Navigate to the repo folder
Set-Location "$PSScriptRoot"

# Pull latest changes from GitHub
git pull origin main

# Run your custom script
# Adjust this line to whatever your script is
python "$PSScriptRoot\launcher.py"

# Optional: log output
$date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"$date - Job ran successfully" | Out-File -Append "job.log"
