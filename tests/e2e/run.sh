#!/usr/bin/env bash
# Simula um PDV completo e testa o HIPAUTO de ponta a ponta (motor, interface e
# executável). Requer Docker. Uso: tests/e2e/run.sh [pasta-para-capturas]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SHOTS="${1:-$ROOT/tests/e2e/capturas}"
mkdir -p "$SHOTS"
IMAGE="${HIPAUTO_IMAGE:-hipauto-build}"
docker run --rm --cap-add SYS_ADMIN --security-opt seccomp=unconfined --security-opt apparmor=unconfined \
  -v "$ROOT:/src:ro" -v "$SHOTS:/shots" "$IMAGE" bash -c '
    set -e
    useradd -m tecnico >/dev/null 2>&1
    chmod 777 /shots
    python3 /src/tests/e2e/fakepdv.py setup & 
    for i in $(seq 100); do [ -f /run/fakepdv/ready ] && break; sleep .1; done
    Xvfb :9 -screen 0 1366x768x24 >/dev/null 2>&1 &
    sleep 1
    su tecnico -c "cd /tmp && PYTHONDONTWRITEBYTECODE=1 PATH=/opt/fakepdv/bin:\$PATH DISPLAY=:9 HIPAUTO_SHOTS=/shots \
      python3 /src/tests/e2e/test_simulacao.py -v"
  '
