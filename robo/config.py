"""Configuração central do Robo Historias.

Credenciais vêm de variáveis de ambiente (GitHub Actions) ou, localmente,
dos arquivos em secrets/ (protegidos pelo .gitignore).
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SECRETS = RAIZ / "secrets"
SAIDA = RAIZ / "saida"
ASSETS = RAIZ / "assets"
HISTORICO = RAIZ / "historico.json"


def _credencial(env: str, arquivo: str) -> str:
    valor = os.environ.get(env, "").strip()
    if valor:
        return valor
    caminho = SECRETS / arquivo
    if caminho.exists():
        return caminho.read_text(encoding="utf-8").strip()
    raise RuntimeError(f"Credencial ausente: defina {env} ou crie secrets/{arquivo}")


def gemini_key() -> str:
    return _credencial("GEMINI_API_KEY", "gemini.key")


def cloudflare_token() -> str:
    return _credencial("CLOUDFLARE_API_TOKEN", "cloudflare.token")


def cloudflare_account() -> str:
    return _credencial("CLOUDFLARE_ACCOUNT_ID", "cloudflare.account")


def youtube_token_json() -> str:
    return _credencial("YOUTUBE_TOKEN_JSON", "token.json")


# Modelos
VOZ_NARRADOR = "Sulafat"  # voz calorosa; troque se preferir outra
MODELO_IMAGEM = "@cf/black-forest-labs/flux-1-schnell"

# Formato do vídeo (Shorts vertical)
LARGURA, ALTURA, FPS = 1080, 1920, 30
CENAS_MIN, CENAS_MAX = 6, 8
DURACAO_ALVO_S = (45, 60)

# Identidade visual fixa do canal
ESTILO_VISUAL = (
    "high-quality 3D animated feature film still, stylized cute characters, "
    "big expressive eyes, soft global illumination, warm cinematic lighting, "
    "vibrant but gentle color palette, shallow depth of field, clean simple "
    "background, family-friendly, wholesome, centered composition"
)
PROIBIDO_VISUAL = (
    "no text, no letters, no watermark, no logos, no faces on objects, rocks, trees or clouds, "
    "animals keep natural animal anatomy with hooves or paws, no human hands, no fingers, "
    "no extra limbs, no scary or violent elements, no real people, "
    "no copyrighted or famous characters"
)

# YouTube
CATEGORIA_YT = "1"  # Film & Animation
IDIOMA = "pt-BR"
# Semana de revisão: privado até 12/11/2026; a partir de 13/11/2026, público automático.
# Uma privacidade escolhida manualmente na execução (botão "Run workflow") sempre tem prioridade.
PUBLICO_A_PARTIR_DE = "2026-11-13"


def _privacidade_padrao() -> str:
    escolhida = os.environ.get("PRIVACIDADE", "").strip()
    if escolhida:
        return escolhida
    import datetime
    from zoneinfo import ZoneInfo
    hoje = datetime.datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    return "public" if hoje >= PUBLICO_A_PARTIR_DE else "private"


PRIVACIDADE_PADRAO = _privacidade_padrao()

# Ordem de fallback para geração de texto (erros temporários 503/429/500)
MODELOS_TEXTO = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.5-flash-lite"]
MODELOS_VOZ = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview"]
ESPERAS_RETRY_S = [5, 15, 45]
