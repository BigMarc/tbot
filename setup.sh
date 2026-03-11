#!/usr/bin/env bash
# setup.sh — Erstellt die Projektstruktur und installiert Abhängigkeiten
set -e

echo "=== Trading Bot Setup ==="

# 1. Python3 prüfen
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 nicht gefunden. Bitte installieren: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# 2. src/ Package erstellen und Module verschieben (falls noch nicht geschehen)
if [ ! -d "src" ]; then
    echo "→ Erstelle src/ Package-Struktur..."
    mkdir -p src
    touch src/__init__.py

    # Module in src/ verschieben (nur wenn sie noch im Root liegen)
    for module in config.py data_feed.py market_analyzer.py signal_engine.py \
                  risk_manager.py paper_broker.py telegram_notifier.py \
                  trade_journal.py scheduler.py; do
        if [ -f "$module" ] && [ ! -f "src/$module" ]; then
            echo "   Verschiebe $module → src/$module"
            mv "$module" "src/$module"
        fi
    done
else
    echo "→ src/ existiert bereits, überspringe."
fi

# 3. Virtual Environment erstellen
if [ ! -d "venv" ]; then
    echo "→ Erstelle Virtual Environment..."
    python3 -m venv venv
else
    echo "→ venv/ existiert bereits, überspringe."
fi

# 4. Abhängigkeiten installieren
echo "→ Installiere Abhängigkeiten..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "   $(pip list --format=columns | wc -l) Pakete installiert."

# 5. Verzeichnisse erstellen
echo "→ Erstelle Verzeichnisse..."
mkdir -p logs data

# 6. .env prüfen
if [ ! -f ".env" ]; then
    echo "→ Erstelle .env Template..."
    cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
EOF
    echo "   WICHTIG: Trage deine Telegram Credentials in .env ein!"
else
    echo "→ .env existiert bereits."
fi

echo ""
echo "=== Setup abgeschlossen ==="
echo "Nächste Schritte:"
echo "  1. source venv/bin/activate"
echo "  2. nano .env   (Telegram Credentials eintragen)"
echo "  3. python3 main.py"
