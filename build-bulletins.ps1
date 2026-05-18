param(
    [string[]]$Issues = @("01", "02", "03", "04", "05", "06", "07")
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSCommandPath

Push-Location $RepoRoot
try {
    foreach ($Issue in $Issues) {
        $CoverTex = "Cover-Art/issue$Issue-cover.tex"
        if (-not (Test-Path $CoverTex)) {
            throw "Missing cover source: $CoverTex"
        }
        # TikZ remember-picture anchors settle on the second pass.
        1..2 | ForEach-Object {
            lualatex -interaction=nonstopmode -halt-on-error -shell-escape -output-directory=Cover-Art $CoverTex
        }
    }

    foreach ($Issue in $Issues) {
        $IssueTex = "Bulletins/issue$Issue.tex"
        if (-not (Test-Path $IssueTex)) {
            throw "Missing issue source: $IssueTex"
        }
        # Hyperref destinations/citation jumps settle cleanly on the second pass.
        1..2 | ForEach-Object {
            lualatex -interaction=nonstopmode -halt-on-error -output-directory=Bulletins $IssueTex
        }
    }

}
finally {
    Pop-Location
}
