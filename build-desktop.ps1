$ErrorActionPreference = 'Stop'
$workspace = (Get-Location).Path
$command = 'apt-get update >/dev/null && apt-get install -y --no-install-recommends python3-pip python3-tk python3-dev binutils xvfb xauth >/dev/null && python3 -m pip install --disable-pip-version-check --no-cache-dir -q pyinstaller==6.15.0 && xvfb-run -a python3 -m unittest discover -s tests && python3 -m PyInstaller --noconfirm --clean HIPAUTO-Desktop.spec && rm -rf build'
docker run --rm --platform linux/amd64 -e DEBIAN_FRONTEND=noninteractive -v "${workspace}:/src" -w /src ubuntu:22.04 bash -lc $command
Get-FileHash dist/HIPAUTO-Desktop -Algorithm SHA256
