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
from robo.traducao import traduzir

ESCOPOS = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TEMPORARIOS = {500, 502, 503, 504}
HASHTAGS = "#Shorts #HistoriaInfantil #HistoriasParaCriancas #AnimacaoInfantil"


def _youtube():
    info = json.loads(config.youtube_token_json())
    cred = Credentials.from_authorized_user_info(info, info.get("scopes") or ESCOPOS)
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
        linhas.append(f"✍️ Roteiro: {roteiro['roteirista']}" + (f" · Edição: {roteiro['editor']}" if roteiro.get("editor") else ""))
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


def _srt(blocos) -> str:
    def ts(s):
        ms = int(round(s * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        seg, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{seg:02d},{ms:03d}"
    return "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{f}\n" for i, (a, b, f) in enumerate(blocos, start=1))


def _enriquecer(yt, video_id: str, roteiro: dict, meta: dict):
    """Títulos/descrições em 15 idiomas e legendas CC (exige a permissão youtube.force-ssl)."""
    if not config.token_tem_escopo(config.ESCOPO_LEGENDAS):
        print("  traduções e legendas CC aguardando nova autorização do YouTube (permissão force-ssl)")
        return
    arq = config.SAIDA / "legendas.json"
    blocos = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
    frases = [b[2] for b in blocos]
    trad = traduzir(meta["titulo"], meta["descricao"], frases, config.IDIOMAS_TRADUCAO)
    if trad:
        try:
            atual = yt.videos().list(part="snippet", id=video_id).execute()["items"][0]["snippet"]
            yt.videos().update(part="snippet,localizations", body={
                "id": video_id,
                "snippet": {"title": atual["title"], "description": atual["description"],
                            "categoryId": atual["categoryId"], "tags": atual.get("tags", []),
                            "defaultLanguage": config.IDIOMA, "defaultAudioLanguage": config.IDIOMA},
                "localizations": {l: {"title": d["titulo"], "description": d["descricao"]} for l, d in trad.items()},
            }).execute()
            print(f"  título e descrição em {len(trad)} idiomas")
        except HttpError as e:
            print(f"  traduções de título/descrição falharam: {str(e)[:200]}")
    faixas = {config.IDIOMA: frases}
    for lang in config.LEGENDAS_CC:
        if lang != config.IDIOMA and (trad.get(lang) or {}).get("frases"):
            faixas[lang] = trad[lang]["frases"]
    for lang, textos in faixas.items():
        if not blocos:
            break
        caminho = config.SAIDA / f"legenda_{lang}.srt"
        caminho.write_text(_srt([(b[0], b[1], t) for b, t in zip(blocos, textos)]), encoding="utf-8")
        try:
            yt.captions().insert(
                part="snippet",
                body={"snippet": {"videoId": video_id, "language": lang, "name": "", "isDraft": False}},
                media_body=MediaFileUpload(str(caminho), mimetype="application/octet-stream"),
            ).execute()
            print(f"  legenda CC enviada: {lang}")
        except HttpError as e:
            print(f"  legenda {lang} falhou: {str(e)[:200]}")


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
    try:
        _enriquecer(yt, video_id, roteiro, meta)
    except Exception as e:
        print(f"  enriquecimento (traduções/legendas) falhou sem afetar a publicação: {str(e)[:200]}")
    _registrar(video_id, roteiro, privacidade)

    estado = yt.videos().list(part="status", id=video_id).execute()["items"][0]["status"]
    print(f"  status: {estado.get('privacyStatus')} | upload: {estado.get('uploadStatus')} "
          f"| infantil: {estado.get('madeForKids')}")
    return video_id


if __name__ == "__main__":
    roteiro = json.loads((config.SAIDA / "roteiro.json").read_text(encoding="utf-8"))
    vid = publicar(config.SAIDA / "video.mp4", roteiro, privacidade="private")
    print(f"Publicado (privado): https://youtube.com/shorts/{vid}")
