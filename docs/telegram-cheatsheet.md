# Telegram Bot API Reference (AI Bot Edition)

IMPORTANT

Before implementing anything, cross-check against the official Telegram Bot API docs:

https://core.telegram.org/bots/api

This document focuses only on the endpoints commonly used by AI assistants, chatbots, document bots, image generators, and voice bots.

---

# Base URL

```text
https://api.telegram.org/bot<TOKEN>
```

Example:

```text
https://api.telegram.org/bot123456:ABCDEF...
```

---

# Bot Setup

## Get Bot Info

```http
GET /getMe
```

```bash
curl "https://api.telegram.org/bot<TOKEN>/getMe"
```

---

## Set Webhook

```http
POST /setWebhook
```

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/setWebhook" \
-d "url=https://api.example.com/telegram/webhook"
```

---

## Set Webhook with Secret Token

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/setWebhook" \
-H "Content-Type: application/json" \
-d '{
  "url": "https://api.example.com/telegram/webhook",
  "secret_token": "super-secret"
}'
```

Telegram will include:

```text
X-Telegram-Bot-Api-Secret-Token
```

on webhook requests.

---

## Get Webhook Info

```http
GET /getWebhookInfo
```

```bash
curl \
"https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

---

## Delete Webhook

```http
POST /deleteWebhook
```

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/deleteWebhook"
```

---

# Development Polling

## Get Updates

Used when you are NOT using webhooks.

```http
GET /getUpdates
```

```bash
curl \
"https://api.telegram.org/bot<TOKEN>/getUpdates"
```

---

# Sending Messages

## Send Text Message

```http
POST /sendMessage
```

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendMessage" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": 123456789,
  "text": "Hello World"
}'
```

---

## Send Markdown Message

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendMessage" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": 123456789,
  "text": "*Hello*",
  "parse_mode": "Markdown"
}'
```

---

# Sending Media

## Send Photo

### Via URL (including S3 Presigned URLs)

```http
POST /sendPhoto
```

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendPhoto" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": 123456789,
  "photo": "https://example.com/image.png",
  "caption": "Generated image"
}'
```

---

### Upload Local Photo

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendPhoto" \
-F chat_id=123456789 \
-F photo=@image.png
```

---

## Send Document

```http
POST /sendDocument
```

### Via URL

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendDocument" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": 123456789,
  "document": "https://example.com/report.pdf"
}'
```

### Upload Local File

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendDocument" \
-F chat_id=123456789 \
-F document=@report.pdf
```

---

## Send Audio

```http
POST /sendAudio
```

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendAudio" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": 123456789,
  "audio": "https://example.com/audio.mp3"
}'
```

---

## Send Voice Message

```http
POST /sendVoice
```

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendVoice" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": 123456789,
  "voice": "https://example.com/voice.ogg"
}'
```

---

## Send Video

```http
POST /sendVideo
```

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendVideo" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": 123456789,
  "video": "https://example.com/video.mp4"
}'
```

---

# UX Helpers

## Typing Indicator

```http
POST /sendChatAction
```

```bash
curl -X POST \
"https://api.telegram.org/bot<TOKEN>/sendChatAction" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": 123456789,
  "action": "typing"
}'
```

Available actions:

```text
typing
upload_photo
upload_document
record_video
upload_video
record_voice
upload_voice
```

---

# Downloading User Media

When users upload:

```text
Photos
PDFs
Voice Notes
Audio
Videos
```

Telegram sends a `file_id`.

---

## Step 1: Get File Metadata

```http
GET /getFile
```

```bash
curl \
"https://api.telegram.org/bot<TOKEN>/getFile?file_id=<FILE_ID>"
```

Response:

```json
{
    "ok": true,
    "result": {
        "file_id": "...",
        "file_size": 94129,
        "file_path": "photos/file_0.jpg"
    }
}
```

---

## Step 2: Download File

```bash
curl -O \
"https://api.telegram.org/file/bot<TOKEN>/photos/file_0.jpg"
```

General format:

```text
https://api.telegram.org/file/bot<TOKEN>/<file_path>
```

---

# Webhook Payload Fields

## Chat ID

```python
update["message"]["chat"]["id"]
```

## User Message

```python
update["message"]["text"]
```

## Photo

```python
update["message"]["photo"][-1]["file_id"]
```

## Document

```python
update["message"]["document"]["file_id"]
```

## Voice

```python
update["message"]["voice"]["file_id"]
```

## Audio

```python
update["message"]["audio"]["file_id"]
```

## Video

```python
update["message"]["video"]["file_id"]
```

---

# Typical AI Bot Flow

```text
User
  ↓
Telegram
  ↓
Webhook
  ↓
FastAPI / Flask / Lambda
  ↓
OpenAI / Claude / Gemini
  ↓
sendMessage()

or

sendPhoto()

or

sendDocument()
```

---

# Endpoints You'll Actually Use

```text
GET    /getMe

POST   /setWebhook
GET    /getWebhookInfo
POST   /deleteWebhook

GET    /getUpdates

POST   /sendMessage
POST   /sendPhoto
POST   /sendDocument
POST   /sendAudio
POST   /sendVoice
POST   /sendVideo

POST   /sendChatAction

GET    /getFile
```

For most AI assistants, these endpoints cover 95%+ of all Telegram bot functionality.
