"""Registro do andamento de cada execução para o painel (docs/painel/dados.json).

O painel (https://techally96.github.io/robo-historias/painel/) lê este arquivo para mostrar a etapa
atual, o resultado e, em caso de erro, uma explicação em português. Tudo aqui é "melhor esforço":
nenhuma falha do painel pode derrubar a geração do vídeo."""
import datetime
import json
import os
import subprocess

from robo import config

ARQUIVO = config.RAIZ / "docs" / "painel" / "dados.json"
MAX_EXECUCOES = 300
_atual = None


def _agora() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _carregar() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"execucoes": []}


def _enviar(mensagem: str) -> None:
    """Grava o arquivo e, dentro do GitHub Actions, envia ao repositório para o painel ver na hora."""
    try:
        dados = _carregar()
        execs = [e for e in dados.get("execucoes", []) if e.get("id") != _atual["id"]]
        execs.append(_atual)
        dados["execucoes"] = execs[-MAX_EXECUCOES:]
        dados["atualizado"] = _agora()
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return
        git = ["git", "-c", "user.name=robo-historias[bot]",
               "-c", "user.email=github-actions[bot]@users.noreply.github.com"]
        for cmd in (git + ["add", str(ARQUIVO)],
                    git + ["commit", "-q", "-m", f"Painel: {mensagem}"],
                    git + ["-c", "rebase.autoStash=true", "pull", "-q", "--rebase", "origin", "main"],
                    git + ["push", "-q", "origin", "HEAD:main"]):
            subprocess.run(cmd, cwd=config.RAIZ, timeout=60, capture_output=True)
    except Exception as e:  # o painel nunca derruba o robô
        print(f"  (painel não atualizado: {type(e).__name__})")


def iniciar() -> None:
    global _atual
    _atual = {
        "id": int(os.environ.get("GITHUB_RUN_ID") or 0) or int(datetime.datetime.now().timestamp()),
        "tentativa": int(os.environ.get("GITHUB_RUN_ATTEMPT") or 1),
        "evento": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "inicio": _agora(),
        "fim": None,
        "situacao": "rodando",
        "etapa": "Preparando",
        "etapas": [{"nome": "Preparando", "inicio": _agora()}],
    }
    _enviar("execução iniciada")


def etapa(nome: str, **extras) -> None:
    if not _atual:
        return
    _atual["etapa"] = nome
    _atual["etapas"].append({"nome": nome, "inicio": _agora()})
    _atual.update({k: v for k, v in extras.items() if v is not None})
    _enviar(nome)


def _imagens_usadas() -> int:
    try:
        from robo import imagens
        return int(imagens._usadas)
    except Exception:
        return 0


def concluir(titulo: str, video: str, **extras) -> None:
    if not _atual:
        return
    _atual.update(situacao="publicado", etapa="Finalizado", fim=_agora(), titulo=titulo, video=video,
                  imagens=_imagens_usadas(), mensagem="Vídeo publicado no canal.")
    _atual.update({k: v for k, v in extras.items() if v is not None})
    _atual["etapas"].append({"nome": "Finalizado", "inicio": _agora()})
    _enviar("vídeo publicado")


def explicar(e: BaseException) -> tuple:
    """Traduz o erro técnico em (explicação em português, o robô se recupera sozinho?)."""
    nome, texto = type(e).__name__, str(e)
    t = texto.lower()
    if "daily free allocation" in t or "neurons" in t:
        return ("A cota gratuita diária de imagens da Cloudflare acabou. Ela renova às 21:00 (Brasília) "
                "e o robô tenta de novo no próximo horário depois disso.", True)
    if "cog prediction failed" in t or "http 409" in t or "http 5" in t:
        return ("O servidor de imagens da Cloudflare teve uma falha momentânea e não respondeu mesmo após "
                "várias tentativas. Não é problema do robô; ele tenta de novo no próximo horário.", True)
    if "nsfw" in t:
        return ("O filtro de segurança da Cloudflare recusou a descrição de uma cena por engano (falso alarme), "
                "mesmo depois de refazer com uma descrição neutra. O robô tenta outra história no próximo horário.", True)
    if nome == "OrcamentoEsgotado":
        return ("Esta execução atingiu o limite de imagens que pode gastar (para sobrar cota para o outro "
                "vídeo do dia). A IA errou muitas cenas; o robô tenta uma história nova no próximo horário.", True)
    if nome == "EspecieDificil":
        return ("A IA de imagem não conseguiu desenhar o animal sorteado nem na segunda história. "
                "Os animais difíceis saem do sorteio e o robô tenta de novo no próximo horário.", True)
    if "incompatíveis com a história" in t:
        return ("Algumas cenas continuaram com erros (animal errado, membros a mais ou texto) mesmo depois "
                "das correções. Para não mostrar imagem errada às crianças, nada foi publicado. "
                "O robô tenta uma história nova no próximo horário.", True)
    if "prazo do roteiro esgotado" in t:
        return ("As IAs de texto (Gemini e Groq) estavam muito lentas ou ocupadas e o roteiro passou de 15 minutos. "
                "O robô desiste para não travar e tenta de novo no próximo horário.", True)
    if "roteiro reprovado" in t:
        return ("O revisor reprovou o roteiro nas 4 tentativas (erro de português, de conteúdo ou de coerência). "
                "O robô escreve uma história nova no próximo horário.", True)
    if "todos os provedores falharam" in t or "sem modelos disponíveis" in t:
        return ("As IAs de texto (Gemini e Groq) estavam fora do ar ou sem cota naquele momento. "
                "Isso costuma passar sozinho; o robô tenta de novo no próximo horário.", True)
    if "invalid_grant" in t or "token has been expired" in t or ("refresh" in t and "token" in t):
        return ("A autorização do canal no YouTube expirou ou foi revogada. É preciso gerar um token novo "
                "(gerar_token.py) e atualizar o segredo YOUTUBE_TOKEN_JSON no GitHub.", False)
    if "quotaexceeded" in t or "uploadlimitexceeded" in t:
        return ("O YouTube recusou o envio por limite diário (cota da API ou de uploads do canal). "
                "O limite renova sozinho no dia seguinte.", True)
    if "limite de shorts" in t:
        return ("O vídeo ficou mais longo que o permitido para Shorts e não foi publicado. "
                "O robô escreve uma história nova no próximo horário.", True)
    if ("401" in t or "403" in t) and any(x in t for x in ("cloudflare", "groq", "youtube", "api")):
        return ("Uma chave de acesso (API) foi recusada. Pode ter expirado ou sido trocada; "
                "confira os segredos do repositório no GitHub.", False)
    return (f"Erro inesperado ({nome}): {texto[:300]}. O robô tenta de novo no próximo horário; "
            "se repetir, peça ao Claude para analisar.", True)


def erro(e: BaseException) -> None:
    if not _atual:
        return
    explicacao, recupera = explicar(e)
    _atual.update(situacao="erro", fim=_agora(), imagens=_imagens_usadas(),
                  mensagem=explicacao, recupera=recupera,
                  tecnico=f"{type(e).__name__}: {str(e)[:500]}",
                  etapa_erro=_atual.get("etapa"))
    _enviar("erro registrado")
