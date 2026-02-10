# Joana Chatbot - WhatsApp Food Ordering Bot

A Flask-based WhatsApp chatbot for Joana Fast Food restaurant, deployed on Railway.

## Features
- WhatsApp Business API integration
- AI-powered order processing with OpenAI
- Multi-language support (English & Arabic)
- Menu item recognition with typo correction
- Supabase database integration
- Voice message transcription

## Deployment
- **Platform**: Railway
- **Region**: Southeast Asia (Singapore)
- **Python Version**: 3.10.6
- **Web Server**: Gunicorn

## Environment Variables Required
- `OPENAI_API_KEY`
- `WHATSAPP_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `SUPABASE_PROJECT_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_ANON_KEY`
- `DEEPGRAM_API_KEY`
- `FLASK_SECRET_KEY`
- `VERIFY_TOKEN`
- `CRON_SECRET`

## Webhook URL
`https://joanachatbot-production.up.railway.app/whatsapp/webhook`

## Recent Updates
- Fixed menu item recognition (Sweet Potato, Chicken, etc.)
- Refined irrelevant terms filtering
- Added menu protection logic
- Configured for Railway deployment
