$ErrorActionPreference = 'Stop'
$src = Split-Path $PSScriptRoot
$out = Join-Path (Split-Path $src) 'VRChat-Translator.zip'
$tmp = Join-Path $env:TEMP ('vrct_share_' + [guid]::NewGuid().ToString('N'))
$dst = Join-Path $tmp 'VRChat-Translator'
New-Item -ItemType Directory -Force (Join-Path $dst 'tools') | Out-Null

Get-ChildItem $src -File |
    Where-Object { $_.Extension -in '.py', '.bat', '.ico', '.exe' -or $_.Name -in 'README.md', 'requirements.txt', 'LICENSE' } |
    Copy-Item -Destination $dst
Get-ChildItem (Join-Path $src 'tools') -File | Copy-Item -Destination (Join-Path $dst 'tools')

$cfg = Join-Path $src 'config.json'
if (Test-Path $cfg) {
    $c = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
    $secrets = @($c.deepl_key, $c.gemini_key, $c.groq_key, $c.mymemory_email) | Where-Object { $_ }
    foreach ($f in Get-ChildItem $dst -Recurse -File) {
        $text = [IO.File]::ReadAllText($f.FullName)
        foreach ($s in $secrets) {
            if ($text.Contains($s)) { throw "a key was found in $($f.Name) - zip NOT created" }
        }
    }
}

if (Test-Path $out) { Remove-Item $out }
Compress-Archive -Path $dst -DestinationPath $out
Remove-Item -Recurse -Force $tmp
Write-Host "Done: $out"
