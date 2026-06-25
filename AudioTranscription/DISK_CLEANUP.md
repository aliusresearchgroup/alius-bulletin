# Disk Cleanup Rules

Date: 2026-06-03

The audio pipeline produces large intermediate files. Keep the small, durable
artifacts in git and treat large source/work media as regenerable unless they
are final published assets.

## Keep

- `profiles/*.json`
- `references/**/*.wav`
- `references/**/*.manifest.json`
- `render_plans/*.json`
- `renders/**/render_manifest.json`
- verified final `renders/**/*.mp3`
- verified final `renders_kokoclone/**/*.mp3`
- scripts and documentation

## Safe To Delete After References Are Cut

- `sources/`
- `work/**/*.wav`
- `work/**/f5_config.toml`
- `work/**/kokoclone/*.concat.txt`
- temporary audition and verification WAVs

The source media can be redownloaded from profile metadata and source-candidate
records. Reference clips are the compact, curated assets needed for repeatable
voice cloning.

## Commands

Delete downloaded source media after references are extracted:

```powershell
$target = Resolve-Path AudioTranscription/sources
Remove-Item -LiteralPath $target.Path -Recurse -Force
New-Item -ItemType Directory -Path AudioTranscription/sources | Out-Null
```

Delete generated work WAVs after verified MP3s/manifests exist:

```powershell
Get-ChildItem AudioTranscription/work -Recurse -File -Include *.wav |
  Remove-Item -Force
```

Before deleting recursively, always verify the resolved target path is inside
`C:\Users\cogpsy-vrlab\Documents\GitHub\ALIUS-bulletin\AudioTranscription`.
