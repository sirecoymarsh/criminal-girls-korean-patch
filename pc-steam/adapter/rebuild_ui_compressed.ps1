$ErrorActionPreference='Stop'
& python 'P:\AI\Codex\projects\criminal-girls-invite-only-ko\adapter\build_encoded_ui.py'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& python 'P:\AI\Codex\projects\criminal-girls-invite-only-ko\adapter\build_common_ui_v2.py'
exit $LASTEXITCODE
