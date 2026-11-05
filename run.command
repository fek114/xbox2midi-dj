#!/bin/bash
# =============================================================================
#  Xbox2MIDI DJ — Tek tıkla başlatıcı
#  Finder'da bu dosyaya ÇİFT TIKLAYIN. İlk açılışta gerekli her şey otomatik
#  ve sessizce kurulur, sonra arayüz açılır.
# =============================================================================
cd "$(dirname "$0")" || exit 1
source "./scripts/bootstrap.sh"

printf "\n  🎮  Xbox2MIDI DJ — macOS Controller Bridge\n\n"

bootstrap_env || { echo; read -r -p "Kapatmak için Enter'a basın…" _; exit 1; }

ok "Arayüz açılıyor… (Bu pencereyi kapatmak uygulamayı da kapatır)"
"$VENV_PY" "$PROJECT_DIR/main.py" 2>>"$LOG_DIR/app.log"
STATUS=$?
if [ $STATUS -ne 0 ]; then
    fail "Uygulama beklenmedik şekilde kapandı (kod $STATUS). Ayrıntılar: logs/app.log"
    tail -n 25 "$LOG_DIR/app.log"
    read -r -p "Kapatmak için Enter'a basın…" _
fi
exit $STATUS
