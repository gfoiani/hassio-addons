#!/bin/bash
# =====================================================================
# Deploy locale del Telegram Bot Relay come container Docker.
#
# Uso:
#   chmod +x deploy_local.sh
#   ./deploy_local.sh
#
# Il file .env deve esistere nella stessa cartella (copia .env.example).
# =====================================================================

set -e

CONTAINER_NAME="telegram-bot-relay"
IMAGE_NAME="telegram-bot-relay"
PORT=8000

# ---------------------------------------------------------------------------
# Controllo prerequisiti
# ---------------------------------------------------------------------------

if [ ! -f ".env" ]; then
  echo "Errore: file .env non trovato."
  echo "Copia .env.example in .env e compila le variabili:"
  echo "  cp .env.example .env"
  exit 1
fi

# Verifica che TELEGRAM_BOT_TOKEN sia impostato
BOT_TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2 | tr -d ' ')
if [[ -z "$BOT_TOKEN" || "$BOT_TOKEN" == "your_bot_token_here" ]]; then
  echo "Errore: TELEGRAM_BOT_TOKEN non impostato nel file .env."
  echo "Ottienilo da @BotFather su Telegram."
  exit 1
fi

# Verifica che ALLOWED_CHAT_IDS non contenga il valore placeholder
CHAT_IDS=$(grep -E '^ALLOWED_CHAT_IDS=' .env | cut -d= -f2 | tr -d ' ')
if [[ -z "$CHAT_IDS" || "$CHAT_IDS" == "your_chat_id_here" ]]; then
  echo "Errore: ALLOWED_CHAT_IDS non impostato nel file .env."
  echo "Trova il tuo chat ID inviando un messaggio a @userinfobot su Telegram."
  exit 1
fi

# Verifica che RELAY_API_KEY sia impostato
API_KEY=$(grep -E '^RELAY_API_KEY=' .env | cut -d= -f2 | tr -d ' ')
if [[ -z "$API_KEY" || "$API_KEY" == "your_secret_key_here" ]]; then
  echo "Errore: RELAY_API_KEY non impostato nel file .env."
  echo "Genera una chiave con: python3 -c \"import secrets; print(secrets.token_hex(32))\""
  exit 1
fi

# ---------------------------------------------------------------------------
# Build immagine
# ---------------------------------------------------------------------------

echo "Building image ${IMAGE_NAME}:latest …"
docker build -t ${IMAGE_NAME}:latest .

# ---------------------------------------------------------------------------
# Rimuovi container esistente (se presente)
# ---------------------------------------------------------------------------

CONTAINER_EXISTS="$(docker ps -a --format '{{.Names}}' | grep -c "^${CONTAINER_NAME}$" || true)"
if [[ $CONTAINER_EXISTS -ge "1" ]]; then
  echo "Rimozione container esistente ${CONTAINER_NAME} …"
  docker rm -f ${CONTAINER_NAME}
fi

# ---------------------------------------------------------------------------
# Avvio container
# ---------------------------------------------------------------------------

echo "Avvio container ${CONTAINER_NAME} sulla porta ${PORT} …"
docker run -d \
  --name ${CONTAINER_NAME} \
  --env-file .env \
  -e PORT=${PORT} \
  -p ${PORT}:${PORT} \
  --restart=unless-stopped \
  --log-opt max-size=20m \
  ${IMAGE_NAME}:latest

echo ""
echo "Relay avviato."
echo ""
echo "Endpoint locali:"
echo "  Health check : http://localhost:${PORT}/health"
echo "  Webhook      : http://localhost:${PORT}/telegram/webhook"
echo "  Commands     : http://localhost:${PORT}/api/commands"
echo ""
echo "Nota: per ricevere messaggi Telegram in locale è necessario un tunnel ngrok:"
echo "  ngrok http ${PORT}"
echo "  Poi aggiorna WEBHOOK_URL in .env con l'URL ngrok e riavvia."
echo ""
echo "Segui i log con:"
echo "  docker logs -f ${CONTAINER_NAME}"
echo ""
docker ps --filter "name=${CONTAINER_NAME}"
