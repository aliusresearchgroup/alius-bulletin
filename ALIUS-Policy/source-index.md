# ALIUS Policy Source Index

This index records how each supplied zip archive was imported. Each archive contained a single `main.tex` file, copied byte-for-byte into the repository path shown below.

| Original archive | Repository file | Type | SHA-256 of extracted `.tex` |
| --- | --- | --- | --- |
| `C:\Users\cogpsy-vrlab\Downloads\ALIUS_Policy.zip` | [versions/undated-baseline-internal-rules.tex](versions/undated-baseline-internal-rules.tex) | Clean baseline snapshot | `1d73b43f38a6665532d9b48f48cc8e21e9a4226bc9d508a3283157612d570da9` |
| `C:\Users\cogpsy-vrlab\Downloads\ALIUS_Policy_changes_April_22.zip` | [changes/2022-04-changes-from-baseline.tex](changes/2022-04-changes-from-baseline.tex) | Tracked-change source | `92a5f03537685e6599ea886b672c14969a5d59747b82b61e4d69bb6d1e4907a0` |
| `C:\Users\cogpsy-vrlab\Downloads\ALIUS_Policy_April_22.zip` | [versions/2022-04-internal-rules.tex](versions/2022-04-internal-rules.tex) | Clean dated snapshot | `e1490fc0107671846e6ac7b13a4c8c6e6117fb250e8ee9968ea448265d034c96` |
| `C:\Users\cogpsy-vrlab\Downloads\ALIUS_Policy_Oct_22__changes_.zip` | [changes/2022-10-changes-from-2022-04.tex](changes/2022-10-changes-from-2022-04.tex) | Tracked-change source | `cd6be652192fa8d4c3716c42a046a499a70a7f2ec5dae2b1bc2c454607334ebd` |
| `C:\Users\cogpsy-vrlab\Downloads\ALIUS_Policy_May2024.zip` | [changes/2024-05-proposed-changes.tex](changes/2024-05-proposed-changes.tex) | Proposal/status-unknown source | `19d09750296b018fb6d3119bf5888d1a96c623d4912152c495e184afd1dcca59` |
| `C:\Users\cogpsy-vrlab\Downloads\ALIUS_Policy_Oct25.zip` | [versions/2025-10-internal-rules.tex](versions/2025-10-internal-rules.tex) | Clean dated snapshot | `c91e2ac71ca323795c8bac04e696a5e6a076a01cf2bd14d95713d64e8a11ff76` |

## Verification Command

From the repository root, verify the imported files with:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath `
  ALIUS-Policy/versions/undated-baseline-internal-rules.tex,`
  ALIUS-Policy/changes/2022-04-changes-from-baseline.tex,`
  ALIUS-Policy/versions/2022-04-internal-rules.tex,`
  ALIUS-Policy/changes/2022-10-changes-from-2022-04.tex,`
  ALIUS-Policy/changes/2024-05-proposed-changes.tex,`
  ALIUS-Policy/versions/2025-10-internal-rules.tex
```
