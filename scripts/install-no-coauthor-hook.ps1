# Install prepare-commit-msg hook to strip Co-authored-by from commits
# Run: .\scripts\install-no-coauthor-hook.ps1
$hook = @'
#!/bin/sh
FILE="$1"
[ -f "$FILE" ] || exit 0
python -c "
import sys
path=sys.argv[1]
with open(path,'r',encoding='utf-8',errors='ignore') as f: lines=f.readlines()
with open(path,'w',encoding='utf-8') as f:
    for L in lines:
        if 'Co-authored-by' not in L and 'cursoragent' not in L.lower(): f.write(L)
" "$FILE"
'@
$hookPath = Join-Path (git rev-parse --git-dir) "hooks\prepare-commit-msg"
$hook | Out-File -FilePath $hookPath -Encoding utf8
Write-Host "Installed: $hookPath" -ForegroundColor Green
Write-Host "Co-authored-by will be stripped from commit messages." -ForegroundColor Gray
