$ErrorActionPreference = 'Stop'
$src = Split-Path $PSScriptRoot
$out = Join-Path (Split-Path $src) 'VRChat Translator Setup.exe'
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$refs = '/r:System.Windows.Forms.dll', '/r:System.IO.Compression.dll', '/r:System.IO.Compression.FileSystem.dll'
$tmp = Join-Path $env:TEMP ('vrct_build_' + [guid]::NewGuid().ToString('N'))
$dst = Join-Path $tmp 'files'
New-Item -ItemType Directory -Force (Join-Path $dst 'tools') | Out-Null
Push-Location $src
try {
    & $csc /nologo /codepage:65001 /target:winexe /optimize+ /win32icon:icon.ico @refs '/out:VRChat Translator.exe' tools\launcher.cs
    if ($LASTEXITCODE) { throw 'launcher build failed' }

    Get-ChildItem $src -File |
        Where-Object { $_.Extension -in '.py', '.bat', '.ico', '.exe' -or $_.Name -in 'README.md', 'requirements.txt', 'LICENSE' } |
        Copy-Item -Destination $dst
    Get-ChildItem (Join-Path $src 'tools') -File | Copy-Item -Destination (Join-Path $dst 'tools')

    foreach ($f in 'config.json', 'usage.json', 'app.log') {
        if (Test-Path (Join-Path $dst $f)) { throw "private file got in: $f" }
    }
    $cfg = Join-Path $src 'config.json'
    if (Test-Path $cfg) {
        $c = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
        $secrets = @($c.deepl_key, $c.gemini_key, $c.groq_key, $c.mymemory_email) | Where-Object { $_ }
        foreach ($f in Get-ChildItem $dst -Recurse -File) {
            $text = [IO.File]::ReadAllText($f.FullName)
            foreach ($s in $secrets) { if ($text.Contains($s)) { throw "a key was found in $($f.Name) - NOT built" } }
        }
    }

    $zip = Join-Path $tmp 'payload.zip'
    Compress-Archive -Path (Join-Path $dst '*') -DestinationPath $zip
    & $csc /nologo /codepage:65001 /target:winexe /optimize+ /win32icon:icon.ico @refs "/resource:$zip,payload.zip" "/out:$out" tools\launcher.cs
    if ($LASTEXITCODE) { throw 'setup exe build failed' }
    Write-Host ("Done: {0} ({1} KB)" -f $out, [int]((Get-Item $out).Length / 1KB))
}
finally {
    Pop-Location
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
