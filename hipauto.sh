#!/usr/bin/env bash
# HIPAUTO: baixa do GitHub somente quando há versão nova e abre o app.
# Uso: bash -c "$(curl -fsSL https://raw.githubusercontent.com/joaofalcone/HIPAUTO/main/hipauto.sh || wget -qO- https://raw.githubusercontent.com/joaofalcone/HIPAUTO/main/hipauto.sh)"
set -eu
URL=https://raw.githubusercontent.com/joaofalcone/HIPAUTO/main/dist/HIPAUTO-Desktop
DIR="${XDG_CACHE_HOME:-$HOME/.cache}/hipauto"
BIN="$DIR/HIPAUTO-Desktop"
mkdir -p "$DIR"
chmod 700 "$DIR"
[ -x "$BIN" ] || rm -f "$DIR/etag"
ETAG="$(cat "$DIR/etag" 2>/dev/null || true)"
PART="$(mktemp "$DIR/.download.XXXXXX")"
HEAD="$PART.h"
trap 'rm -f "$PART" "$HEAD"' EXIT

# Baixa com curl ou wget (o Ubuntu Desktop traz só o wget). Responde 200, 304 ou falha.
fetch() {
    if command -v curl >/dev/null 2>&1; then
        set -- -fsSL --retry 3 --connect-timeout 10 -D "$HEAD" -o "$PART" -w "%{http_code}"
        [ -n "$ETAG" ] && set -- "$@" -H "If-None-Match: $ETAG"
        curl "$@" "$URL"
    elif command -v wget >/dev/null 2>&1; then
        set -- -q -S --tries=3 --timeout=10 -O "$PART"
        [ -n "$ETAG" ] && set -- "$@" "--header=If-None-Match: $ETAG"
        wget "$@" "$URL" 2>"$HEAD" || true
        code="$(tr -d '\r' < "$HEAD" | sed -n 's/^ *HTTP\/[0-9.]* \([0-9][0-9][0-9]\).*/\1/p' | tail -n1)"
        case "$code" in 200|304) printf %s "$code" ;; *) return 1 ;; esac
    else
        echo "HIPAUTO: instale curl ou wget" >&2
        return 1
    fi
}

if CODE="$(fetch)"; then
    if [ "$CODE" = 200 ]; then
        if [ "$(head -c4 "$PART" | od -An -tx1 | tr -d ' \n')" != 7f454c46 ]; then
            echo "HIPAUTO: download inválido" >&2
            exit 1
        fi
        chmod 700 "$PART"
        mv -f "$PART" "$BIN"
        tr -d '\r' < "$HEAD" | sed -n 's/^ *[Ee][Tt][Aa][Gg]: *//p' | tail -n1 > "$DIR/etag"
    fi
elif [ -x "$BIN" ]; then
    echo "HIPAUTO: servidor indisponível, abrindo a versão em cache" >&2
else
    echo "HIPAUTO: não foi possível baixar" >&2
    exit 1
fi
exec "$BIN" "$@"
