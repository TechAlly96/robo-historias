"""Gera secrets/token.json (autorização OAuth do YouTube). Rodar uma única vez."""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

RAIZ = Path(__file__).resolve().parent.parent
CLIENT = RAIZ / "secrets" / "client_secret.json"
TOKEN = RAIZ / "secrets" / "token.json"
ESCOPOS = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), ESCOPOS)
cred = flow.run_local_server(
    host="localhost",
    port=8085,
    open_browser=False,
    access_type="offline",
    prompt="consent",
    authorization_prompt_message=(
        "\n>>> Copie o link abaixo, abra no navegador do celular e autorize "
        "com a conta techally96@gmail.com:\n\n{url}\n"
    ),
    success_message="Autorizado! Pode voltar ao Termux.",
)

TOKEN.write_text(cred.to_json())
TOKEN.chmod(0o600)

yt = build("youtube", "v3", credentials=cred)
canal = yt.channels().list(part="snippet", mine=True).execute()
itens = canal.get("items", [])
print("\nToken salvo em secrets/token.json")
print("Refresh token presente:", bool(cred.refresh_token))
print("Canal:", itens[0]["snippet"]["title"] if itens else "NENHUM CANAL NESTA CONTA")
