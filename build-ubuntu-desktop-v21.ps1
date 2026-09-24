$ErrorActionPreference = 'Stop'
$workspace = (Get-Location).Path
$command = 'apt-get update >/dev/null && apt-get install -y --no-install-recommends python3-pip python3-tk python3-dev binutils >/dev/null && python3 -m pip install --disable-pip-version-check --no-cache-dir pyinstaller==6.15.0 >/dev/null && python3 -m PyInstaller --noconfirm --clean HIPAUTO-Desktop-V21.spec'
docker run --rm --platform linux/amd64 -e DEBIAN_FRONTEND=noninteractive -e TZ=Etc/UTC -v "${workspace}:/src" -w /src ubuntu:22.04 bash -lc $command
Write-Host "HIPAUTO Desktop V21 criado em dist/HIPAUTO-Desktop"
