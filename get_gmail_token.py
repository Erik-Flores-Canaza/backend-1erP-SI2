"""
Script para obtener un nuevo refresh_token de Gmail OAuth.
Úsalo cuando quieras cambiar la cuenta de envío de correos.

Pasos:
  1. Ejecuta: python get_gmail_token.py
  2. Se abrirá el navegador — inicia sesión con la cuenta nueva
  3. Copia el refresh_token que aparece en la consola
  4. Pégalo en .env (GMAIL_REFRESH_TOKEN) o en Railway
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.getenv("GMAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: Faltan GMAIL_CLIENT_ID o GMAIL_CLIENT_SECRET en el .env")
    exit(1)

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(
    client_config,
    scopes=["https://www.googleapis.com/auth/gmail.send"],
)

creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

print("\n" + "=" * 60)
print("✓ Autenticación exitosa")
print("=" * 60)
print(f"\nCuenta:        {creds.token}")
print(f"\nRefresh Token: {creds.refresh_token}")
print("\nCopia el refresh_token de arriba y ponlo en:")
print("  .env             → GMAIL_REFRESH_TOKEN=<token>")
print("  Railway          → Variable GMAIL_REFRESH_TOKEN")
print("  Y actualiza      → GMAIL_SENDER_EMAIL=<la cuenta nueva>")
print("=" * 60)
