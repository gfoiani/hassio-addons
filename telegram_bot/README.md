# Telegram Bot Relay

Servizio FastAPI che funge da ponte tra Telegram e il trading bot su Raspberry Pi.

Il Raspberry Pi non è raggiungibile direttamente da internet, quindi tutta la comunicazione passa attraverso questo relay ospitato su **Render** (o eseguito in locale per sviluppo).

```sh
Utente ──Telegram──► Relay (Render)  ◄── polling ── Trading Bot (RPi)
                           │
                           └──► POST /api/notify        → messaggio Telegram all'utente
                                GET  /api/commands      → comandi pendenti
                                POST /api/command-result → risposta all'utente
```

---

## Prerequisiti

- Python 3.11+
- Un bot Telegram creato tramite [@BotFather](https://t.me/BotFather)
- Il proprio chat ID Telegram (ottenerlo da [@userinfobot](https://t.me/userinfobot))

---

## Esecuzione in locale

### Opzione A – Docker (consigliata)

```bash
# 1. Configura le variabili d'ambiente
cp .env.example .env
# Apri .env e compila TELEGRAM_BOT_TOKEN, RELAY_API_KEY, ALLOWED_CHAT_IDS

# 2. Build e avvio
chmod +x deploy_local.sh
./deploy_local.sh

# 3. Segui i log
docker logs -f telegram-bot-relay
```

Il relay è disponibile su `http://localhost:8000`.

Per ricevere messaggi Telegram in locale avvia ngrok in un secondo terminale:

```bash
ngrok http 8000
# Copia l'URL https://xxx.ngrok-free.app in WEBHOOK_URL nel .env, poi riavvia:
./deploy_local.sh
```

---

### Opzione B – Python diretto

### 1. Crea e attiva un virtual environment

```bash
cd telegram_bot
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# oppure: venv\Scripts\activate  # Windows
```

### 2. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 3. Configura le variabili d'ambiente

```bash
cp .env.example .env
```

Apri `.env` e compila:

| Variabile | Descrizione |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Token fornito da @BotFather |
| `RELAY_API_KEY` | Chiave segreta arbitraria (deve coincidere con `TELEGRAM_API_KEY` nel bot HA) |
| `ALLOWED_CHAT_IDS` | Il tuo chat ID Telegram (es. `123456789`) |
| `WEBHOOK_URL` | Vuoto in locale (vedi sezione ngrok sotto) |

Carica il file `.env` nell'ambiente:

```bash
export $(grep -v '^#' .env | grep -v '^$' | xargs)
```

### 4. Avvia il server

```bash
uvicorn main:app --reload --port 8000
```

Il server è ora raggiungibile su `http://localhost:8000`.

Verifica che funzioni:

```bash
curl http://localhost:8000/health
```

Risposta attesa:

```json
{"status": "ok", "queue_size": 0, "known_chats": 1, "timestamp": "..."}
```

---

## Ricezione messaggi Telegram in locale (ngrok)

Telegram non può inviare messaggi a `localhost`. Per testare il webhook in locale usa **ngrok**, che espone il server locale su un URL pubblico.

### Installa ngrok

```bash
# macOS
brew install ngrok

# oppure scarica da https://ngrok.com/download
```

### Avvia il tunnel

```bash
ngrok http 8000
```

ngrok mostrerà un URL pubblico tipo `https://abc123.ngrok-free.app`.

### Registra il webhook con Telegram

Con il relay già avviato, imposta `WEBHOOK_URL` e riavvialo:

```bash
# Nel file .env
WEBHOOK_URL=https://abc123.ngrok-free.app

# Ricarica e riavvia
export $(grep -v '^#' .env | grep -v '^$' | xargs)
uvicorn main:app --reload --port 8000
```

All'avvio il relay registra automaticamente il webhook su Telegram.
Ora i messaggi inviati al bot arrivano al tuo server locale.

---

## Testare gli endpoint REST

Gli endpoint `/api/*` richiedono l'header `X-API-Key` con il valore di `RELAY_API_KEY`.

### Inviare una notifica broadcast

```bash
curl -X POST http://localhost:8000/api/notify \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_key_here" \
  -d '{"text": "✅ <b>Test notifica</b> – funziona!"}'
```

### Leggere i comandi in coda

```bash
curl http://localhost:8000/api/commands \
  -H "X-API-Key: your_secret_key_here"
```

### Inviare una risposta a un utente specifico

```bash
curl -X POST http://localhost:8000/api/command-result \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_key_here" \
  -d '{"chat_id": 123456789, "text": "Risposta al tuo comando."}'
```

---

## Deploy su Render

1. Crea un account su [render.com](https://render.com) (piano free sufficiente).
2. Crea un nuovo **Web Service** collegato a questo repository.
3. Imposta:
   - **Root directory**: `telegram_bot`
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Nella sezione **Environment**, aggiungi le variabili:
   - `TELEGRAM_BOT_TOKEN`
   - `RELAY_API_KEY`
   - `ALLOWED_CHAT_IDS`
   - `WEBHOOK_URL` → l'URL del servizio Render stesso (es. `https://trading-bot-telegram-relay.onrender.com`)
5. Fai il deploy. Il webhook viene registrato automaticamente all'avvio.

In alternativa al punto 2–3, puoi usare il file `render.yaml` già incluso:
il repository viene rilevato automaticamente da Render se connetti il repo GitHub.

---

## Comandi Telegram disponibili

| Comando | Descrizione |
| --- | --- |
| `/start` o `/help` | Mostra la lista dei comandi |
| `/status` | Posizioni aperte e P&L non realizzato |
| `/halt` | Blocca l'apertura di nuove posizioni |
| `/resume` | Riprende il trading dopo un halt |
| `/close SYMBOL` | Chiude manualmente una posizione (es. `/close AAPL.US`) |
