OPENING_HOURS = {  # daily opening hours (24h format)
    "mon": ("11:00", "23:59"),
    "tue": ("11:00", "23:59"),
    "wed": ("11:00", "23:59"),
    "thu": ("11:00", "23:59"),
    "fri": ("13:00", "23:59"),
    "sat": ("11:00", "23:59"),
    "sun": ("11:00", "23:59"),
}
VAT_PERCENT = 15  # e.g., KSA 15%
CURRENCY = "SAR"

# rude-words seeding (EN + AR) — keep short; prod me expand
ABUSE_BLOCKLIST = [
    "stupid","idiot","shut up","bastard","fool",
    "غبي","اخرس","قذر","تافه"
]

# language codes we accept
SUPPORTED_LANGS = ["en","ar"]

# fake payment URL base (demo)
PAY_URL_BASE = "https://pay.example.com/invoice?id="
