"""Pipeline completo: roteiro → imagens → narração → montagem → publicação."""
import json
import os
import shutil
import datetime
from zoneinfo import ZoneInfo

from robo import config
from robo.imagens import gerar_imagens
from robo.montagem import montar_video
from robo.narracao import gerar_narracao
from robo.publicar import publicar
from robo.roteiro import gerar_roteiro


FUSO = ZoneInfo("America/Sao_Paulo")


def _turno(dt) -> str:
    return "manhã" if 5 <= dt.hour < 11 else "almoço" if 11 <= dt.hour < 15 else "noite"


def _ja_publicado_neste_turno() -> bool:
    if not config.HISTORICO.exists():
        return False
    agora = datetime.datetime.now(FUSO)
    for h in json.loads(config.HISTORICO.read_text(encoding="utf-8")):
        try:
            dt = datetime.datetime.fromisoformat(h["data"]).astimezone(FUSO)
        except (KeyError, ValueError):
            continue
        if dt.date() == agora.date() and _turno(dt) == _turno(agora):
            return True
    return False


IAS = {"gemini": "Google", "groq": "Groq", "cloudflare": "Cloudflare"}


def _nome_ia(ident: str) -> str:
    provedor, _, modelo = ident.partition(":")
    return f"{modelo.split('/')[-1]} ({IAS.get(provedor, provedor)})"


def _escolher_estudio() -> str:
    """Rodízio: o estúdio usado há mais tempo vai ao ar (fase 4 troca por competição por audiência)."""
    forcado = os.environ.get("ESTUDIO", "").strip()
    if forcado in config.ESTUDIOS:
        return forcado
    ultimo = {}
    if config.HISTORICO.exists():
        for i, h in enumerate(json.loads(config.HISTORICO.read_text(encoding="utf-8"))):
            if h.get("estudio"):
                ultimo[h["estudio"]] = i
    return min(config.ESTUDIOS, key=lambda e: ultimo.get(e, -1))


def main():
    if not os.environ.get("FORCAR") and _ja_publicado_neste_turno():
        print("O vídeo deste turno já foi publicado; nada a fazer.")
        return
    if config.SAIDA.exists():
        shutil.rmtree(config.SAIDA)
    config.SAIDA.mkdir(parents=True)

    print("1/5 Roteiro")
    estudio_id = _escolher_estudio()
    estudio = config.ESTUDIOS[estudio_id]
    config.ORDEM_TEXTO = tuple(estudio["ordem_texto"])
    config.UM_PERSONAGEM_POR_CENA = estudio.get("um_personagem_por_cena", False)
    print(f"  {estudio['nome']}")
    roteiro = gerar_roteiro()
    roteiro.update(
        estudio=estudio_id, estudio_nome=estudio["nome"], modelo_imagem=estudio["modelo_imagem"],
        imagem_credito=estudio["imagem_credito"], hashtags_estudio=estudio["hashtags"],
        credito_tela=f"{estudio['nome']} · {estudio['imagem_credito']} · {_nome_ia(roteiro['roteirista'])}",
    )
    (config.SAIDA / "roteiro.json").write_text(
        json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {roteiro['titulo']} ({len(roteiro['cenas'])} cenas)")

    print("2/5 Imagens")
    gerar_imagens(roteiro)
    if roteiro.get("cenas_reserva_flux"):
        cenas = ", ".join(map(str, roteiro["cenas_reserva_flux"]))
        novo = f"{roteiro['imagem_credito']} + {config.ESTUDIOS['flux']['imagem_credito']} (cenas {cenas})"
        roteiro["credito_tela"] = roteiro["credito_tela"].replace(roteiro["imagem_credito"], novo)
        roteiro["imagem_credito"] = novo

    print("3/5 Narração")
    gerar_narracao(roteiro)

    print("4/5 Montagem")
    video, duracao = montar_video(roteiro)
    if duracao > 175:
        raise RuntimeError(f"Vídeo com {duracao:.0f}s passa do limite de Shorts")

    print("5/5 Publicação")
    vid = publicar(video, roteiro, os.environ.get("PRIVACIDADE") or None)
    url = f"https://youtube.com/shorts/{vid}"
    print(f"Concluído: {url}")

    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"## {roteiro['titulo']}\n\n- Vídeo: {url}\n- Duração: {duracao:.1f}s\n"
                    f"- Moral: {roteiro['moral']}\n")


if __name__ == "__main__":
    main()
