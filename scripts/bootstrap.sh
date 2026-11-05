#!/bin/bash
# =============================================================================
#  Xbox2MIDI DJ — ortak ortam hazırlayıcı (run.command ve build_app.command
#  tarafından `source` edilir). Kullanıcıya hiçbir şey sormaz.
#
#  * Uygun bir Python 3.9+ bulur (Homebrew → python.org → sistem)
#  * Proje içinde .venv oluşturur (yoksa / bozuksa)
#  * requirements.txt değiştiyse bağımlılıkları sessizce kurar
#  Sonuç: $VENV_PY değişkeni hazır sanal ortam yorumlayıcısını gösterir.
# =============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
SETUP_LOG="$LOG_DIR/setup.log"
REQ_FILE="$PROJECT_DIR/requirements.txt"
STAMP_FILE="$VENV_DIR/.requirements.sha"
mkdir -p "$LOG_DIR"

c_reset=$'\033[0m'; c_dim=$'\033[2m'; c_green=$'\033[32m'; c_cyan=$'\033[36m'; c_red=$'\033[31m'
say()  { printf "%s▸%s %s\n" "$c_cyan" "$c_reset" "$*"; }
ok()   { printf "%s✓%s %s\n" "$c_green" "$c_reset" "$*"; }
fail() { printf "%s✗ %s%s\n" "$c_red" "$*" "$c_reset"; }

dialog() {
    # $1 = mesaj
    /usr/bin/osascript -e "display dialog \"$1\" buttons {\"Tamam\"} default button 1 with icon caution with title \"Xbox2MIDI DJ\"" >/dev/null 2>&1
}

find_python() {
    local candidates=(
        "/opt/homebrew/bin/python3"
        "/usr/local/bin/python3"
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
        "$(command -v python3 2>/dev/null)"
        "/usr/bin/python3"
    )
    local c
    for c in "${candidates[@]}"; do
        [ -n "$c" ] && [ -x "$c" ] || continue
        if "$c" -c 'import sys, venv; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
            echo "$c"
            return 0
        fi
    done
    return 1
}

req_hash() { /usr/bin/shasum -a 256 "$REQ_FILE" | awk '{print $1}'; }

bootstrap_env() {
    if [ "$(uname -s)" != "Darwin" ]; then
        fail "Bu uygulama yalnızca macOS içindir."; return 1
    fi

    # 1) Sanal ortam sağlam mı?
    if [ -x "$VENV_PY" ] && "$VENV_PY" -c 'import sys' >/dev/null 2>&1; then
        :
    else
        rm -rf "$VENV_DIR"
        local PY
        PY="$(find_python)" || {
            fail "Python 3 bulunamadı."
            dialog "Python 3 bulunamadı.\n\nmacOS sizden 'Komut Satırı Geliştirici Araçları'nı yüklemenizi isterse 'Yükle'ye basın ya da python.org adresinden Python indirin. Ardından run.command'ı tekrar çalıştırın."
            /usr/bin/open "https://www.python.org/downloads/macos/" >/dev/null 2>&1
            return 1
        }
        say "Sanal ortam oluşturuluyor ($("$PY" --version 2>&1))…"
        "$PY" -m venv "$VENV_DIR" >>"$SETUP_LOG" 2>&1 || {
            fail "Sanal ortam oluşturulamadı. Ayrıntılar: logs/setup.log"
            dialog "Sanal ortam oluşturulamadı. Ayrıntılar logs/setup.log dosyasında."
            return 1
        }
    fi

    # 2) Bağımlılıklar güncel mi?
    local want have=""
    want="$(req_hash)"
    [ -f "$STAMP_FILE" ] && have="$(cat "$STAMP_FILE")"
    if [ "$want" != "$have" ]; then
        say "Bağımlılıklar kuruluyor (yalnızca ilk çalıştırmada, ~1 dk)…"
        {
            echo "==== $(date) ===="
            "$VENV_PY" -m pip install --upgrade pip --disable-pip-version-check
            "$VENV_PY" -m pip install --disable-pip-version-check --prefer-binary -r "$REQ_FILE"
        } >>"$SETUP_LOG" 2>&1
        if [ $? -ne 0 ]; then
            fail "Bağımlılık kurulumu başarısız. İnternet bağlantınızı kontrol edin. Ayrıntılar: logs/setup.log"
            dialog "Bağımlılıklar kurulamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.\n\nAyrıntılar: logs/setup.log"
            return 1
        fi
        echo "$want" > "$STAMP_FILE"
        ok "Bağımlılıklar hazır."
    fi
    return 0
}
