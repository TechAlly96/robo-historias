"""Publica o vídeo no YouTube (upload retomável) e registra no histórico."""
import datetime
import json
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from robo import config

ESCOPOS = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TEMPORARIOS = {500, 502, 503, 504}
HASHTAGS = "#Shorts #HistoriaInfantil #HistoriasParaCriancas #AnimacaoInfantil"


def _youtube():
    info = json.loads(config.youtube_token_json())
    cred = Credentials.from_authorized_user_info(info, ESCOPOS)
    if not cred.valid:
        cred.refresh(Request())
    return build("youtube", "v3", credentials=cred, cache_discovery=False)


def _limpo(texto: str, limite: int) -> str:
    return texto.replace("<", "").replace(">", "").strip()[:limite]


def _versiculo(roteiro: dict) -> str:
    v = roteiro.get("versiculo")
    return f"📖 \"{v['texto']}\" ({v['ref']})\n\n" if v else ""


def _creditos(roteiro: dict) -> str:
    if not roteiro.get("estudio_nome"):
        return ""
    linhas = [f"🎬 {roteiro['estudio_nome']}", f"🎨 Imagens: {roteiro.get('imagem_credito', '')}"]
    if roteiro.get("roteirista"):
        linhas.append(f"✍️ Roteiro: {roteiro['roteirista']}")
    if roteiro.get("voz"):
        linhas.append(f"🎙️ Voz: {roteiro['voz']}")
    return "\n".join(linhas) + "\n\n"


def _metadados(roteiro: dict) -> dict:
    titulo = _limpo(roteiro["titulo"], 100)
    if "#shorts" not in titulo.lower() and len(titulo) <= 90:
        titulo += " #Shorts"
    descricao = _limpo(
        f"{roteiro['descricao']}\n\n"
        f"✨ Moral da história: {roteiro['moral']}\n\n"
        f"{_versiculo(roteiro)}"
        f"{_creditos(roteiro)}"
        "História infantil original, criada com inteligência artificial "
        "(roteiro, imagens e narração).\n"
        "Um novo episódio todos os dias!\n\n"
        f"{HASHTAGS} {' '.join(roteiro.get('hashtags_estudio', []))}",
        5000,
    )
    tags, soma = [], 0
    for tag in [*roteiro.get("tags", []), "história infantil", "animação", "fábula"]:
        tag = _limpo(tag.lstrip("#"), 60)
        if tag and tag.lower() not in {t.lower() for t in tags} and soma + len(tag) <= 450:
            tags.append(tag)
            soma += len(tag) + 1
    return {"titulo": titulo, "descricao": descricao, "tags": tags}


def _registrar(video_id: str, roteiro: dict, privacidade: str):
    historico = []
    if config.HISTORICO.exists():
        historico = json.loads(config.HISTORICO.read_text(encoding="utf-8"))
    historico.append({
        "data": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "id": video_id,
        "url": f"https://youtube.com/shorts/{video_id}",
        "titulo": roteiro["titulo"],
        "moral": roteiro["moral"],
        "privacidade": privacidade,
        "materia": roteiro.get("materia"),
        "topico": roteiro.get("topico"),
        "valor": roteiro.get("valor"),
        "especie": roteiro.get("especie"),
        "versiculo": roteiro.get("versiculo"),
        "resumo": roteiro.get("resumo"),
        "estudio": roteiro.get("estudio"),
        "roteirista": roteiro.get("roteirista"),
        "voz": roteiro.get("voz"),
        "modelo_imagem": roteiro.get("modelo_imagem"),
    })
    config.HISTORICO.write_text(json.dumps(historico, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publicar(video, roteiro: dict, privacidade: str | None = None) -> str:
    privacidade = privacidade or config.PRIVACIDADE_PADRAO
    meta = _metadados(roteiro)
    yt = _youtube()
    corpo = {
        "snippet": {
            "title": meta["titulo"],
            "description": meta["descricao"],
            "tags": meta["tags"],
            "categoryId": config.CATEGORIA_YT,
            "defaultLanguage": config.IDIOMA,
            "defaultAudioLanguage": config.IDIOMA,
        },
        "status": {
            "privacyStatus": privacidade,
            "selfDeclaredMadeForKids": True,
            "containsSyntheticMedia": True,
            "embeddable": True,
        },
    }
    midia = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    pedido = yt.videos().insert(part="snippet,status", body=corpo, media_body=midia)

    resposta, tentativas = None, 0
    while resposta is None:
        try:
            progresso, resposta = pedido.next_chunk()
            if progresso:
                print(f"  enviando... {int(progresso.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in TEMPORARIOS and tentativas < 5:
                tentativas += 1
                espera = 2 ** tentativas
                print(f"  erro temporário {e.resp.status}, nova tentativa em {espera}s")
                time.sleep(espera)
                continue
            raise

    video_id = resposta["id"]
    _registrar(video_id, roteiro, privacidade)

    estado = yt.videos().list(part="status", id=video_id).execute()["items"][0]["status"]
    print(f"  status: {estado.get('privacyStatus')} | upload: {estado.get('uploadStatus')} "
          f"| infantil: {estado.get('madeForKids')}")
    return video_id


if __name__ == "__main__":
    roteiro = json.loads((config.SAIDA / "roteiro.json").read_text(encoding="utf-8"))
    vid = publicar(config.SAIDA / "video.mp4", roteiro, privacidade="private")
    print(f"Publicado (privado): https://youtube.com/shorts/{vid}")
