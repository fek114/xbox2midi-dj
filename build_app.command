#!/bin/bash
# =============================================================================
#  Xbox2MIDI DJ — Bağımsız macOS uygulaması (.app) derleyici
#  Çift tıklayın: dist/Xbox2MIDI DJ.app oluşturulur ve Finder'da gösterilir.
#  Oluşan .app'i Uygulamalar klasörüne sürükleyebilirsiniz; Python gerektirmez.
# =============================================================================
cd "$(dirname "$0")" || exit 1
source "./scripts/bootstrap.sh"

printf "\n  🛠   Xbox2MIDI DJ — .app derleniyor\n\n"
bootstrap_env || { read -r -p "Kapatmak için Enter'a basın…" _; exit 1; }

say "PyInstaller hazırlanıyor…"
"$VENV_PY" -m pip install --disable-pip-version-check -q "pyinstaller>=6.3" >>"$SETUP_LOG" 2>&1 || {
    fail "PyInstaller kurulamadı (logs/setup.log)"; read -r -p "Enter…" _; exit 1; }

say "Derleniyor (1–3 dk)…"
"$VENV_PY" -m PyInstaller --noconfirm --clean --log-level WARN \
    --distpath "$PROJECT_DIR/dist" --workpath "$PROJECT_DIR/build" \
    "$PROJECT_DIR/Xbox2MIDI.spec" 2>&1 | tee "$LOG_DIR/build.log"

APP="$PROJECT_DIR/dist/Xbox2MIDI DJ.app"
if [ -d "$APP" ]; then
    # Yerel derleme: karantina bayrağını temizle, ad-hoc imzala (Apple Silicon zorunluluğu)
    /usr/bin/xattr -cr "$APP" 2>/dev/null
    /usr/bin/codesign --force --deep --sign - "$APP" >>"$LOG_DIR/build.log" 2>&1
    ok "Hazır: dist/Xbox2MIDI DJ.app"
    /usr/bin/open -R "$APP"
else
    fail "Derleme başarısız. Ayrıntılar: logs/build.log"
    read -r -p "Kapatmak için Enter'a basın…" _
    exit 1
fi
