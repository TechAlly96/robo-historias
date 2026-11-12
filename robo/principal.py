"""Pipeline completo: roteiro → imagens → narração → montagem → publicação."""
import json
import os
import shutil
import datetime
from zoneinfo import ZoneInfo

from robo import config
from robo import curriculo
from robo import painel
from robo.imagens import EspecieDificil, gerar_imagens
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


JANELA_HORAS = (0, 24)      # sem restrição de horário: o GitHub chega a atrasar as execuções em horas
MAX_POR_DIA = 2             # vídeos por dia no plano gratuito
INTERVALO_MIN_HORAS = 4     # distância mínima entre dois vídeos
DIFICEIS = config.HISTORICO.parent / "especies_dificeis.json"
USO_IMAGENS = config.HISTORICO.parent / "uso_imagens.json"
IMAGENS_POR_DIA = 50        # ~10 mil neurônios/dia ÷ ~175 por imagem FLUX (4 passos), com folga
MINIMO_PARA_VIDEO = 10      # 7 cenas + algumas correções


def _hoje_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _uso() -> dict:
    try:
        return json.loads(USO_IMAGENS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _salvar_uso() -> None:
    """Soma as imagens desta execução ao total do dia (roda até quando a execução falha)."""
    from robo import imagens
    if not imagens._usadas and not imagens.COTA_ESGOTADA:
        return
    uso = _uso()
    dia = _hoje_utc()
    uso = {d: n for d, n in uso.items() if d >= (datetime.date.fromisoformat(dia) - datetime.timedelta(days=7)).isoformat()}
    uso[dia] = uso.get(dia, 0) + imagens._usadas
    if imagens.COTA_ESGOTADA:
        uso[dia] = max(uso[dia], IMAGENS_POR_DIA)
    USO_IMAGENS.write_text(json.dumps(uso, indent=2) + "\n", encoding="utf-8")
    print(f"  imagens usadas hoje (dia da cota): {uso[dia]} de ~{IMAGENS_POR_DIA}")


def _motivo_para_nao_publicar():
    """Agenda robusta: o GitHub atrasa ou pula horários, então o robô é acordado várias vezes
    e decide aqui se ainda falta vídeo hoje. Retorna o motivo para não publicar, ou None."""
    agora = datetime.datetime.now(datetime.timezone.utc)  # o "dia" é o da cota da Cloudflare (UTC)
    if not (JANELA_HORAS[0] <= agora.hour < JANELA_HORAS[1]):
        return f"fora da janela de publicação ({JANELA_HORAS[0]}h–{JANELA_HORAS[1]}h de Brasília)"
    if not config.HISTORICO.exists():
        return None
    datas = []
    for h in json.loads(config.HISTORICO.read_text(encoding="utf-8")):
        try:
            datas.append(datetime.datetime.fromisoformat(h["data"]).astimezone(datetime.timezone.utc))
        except (KeyError, ValueError, TypeError):
            continue
    hoje = [d for d in datas if d.date() == agora.date()]
    if len(hoje) >= MAX_POR_DIA:
        return f"os {MAX_POR_DIA} vídeos de hoje já foram publicados"
    if datas and (agora - max(datas)).total_seconds() < INTERVALO_MIN_HORAS * 3600:
        return f"o último vídeo saiu há menos de {INTERVALO_MIN_HORAS} horas"
    return None


def _dificeis() -> dict:
    try:
        return json.loads(DIFICEIS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _excluir_especies(nomes) -> None:
    """Tira do sorteio os animais que a IA de imagem deste estúdio não desenha bem."""
    restantes = [e for e in curriculo.ESPECIES if e[0] not in nomes]
    if len(restantes) >= 5:
        curriculo.ESPECIES[:] = restantes


IAS = {"gemini": "Google", "groq": "Groq", "cloudflare": "Cloudflare"}


def _nome_ia(ident: str) -> str:
    provedor, _, modelo = ident.partition(":")
    return f"{modelo.split('/')[-1]} ({IAS.get(provedor, provedor)})"


def _escolher_estudio() -> str:
    """Rodízio entre estúdios, respeitando o intervalo mínimo dos motores mais caros (cota da Cloudflare)."""
    forcado = os.environ.get("ESTUDIO", "").strip()
    if forcado in config.ESTUDIOS:
        return forcado
    hist = json.loads(config.HISTORICO.read_text(encoding="utf-8")) if config.HISTORICO.exists() else []
    ultimo, ultima_data = {}, {}
    for i, h in enumerate(hist):
        if h.get("estudio"):
            ultimo[h["estudio"]] = i
            try:
                ultima_data[h["estudio"]] = datetime.datetime.fromisoformat(h["data"])
            except (KeyError, ValueError):
                pass
    agora = datetime.datetime.now(datetime.timezone.utc)

    def liberado(e):
        horas = config.ESTUDIOS[e].get("intervalo_min_horas", 0)
        d = ultima_data.get(e)
        return not horas or d is None or (agora - d).total_seconds() >= horas * 3600

    candidatos = [e for e in config.ESTUDIOS if liberado(e)] or ["flux"]
    return min(candidatos, key=lambda e: ultimo.get(e, -1))


def main():
    if not os.environ.get("FORCAR"):
        motivo = _motivo_para_nao_publicar()
        if motivo:
            print(f"Nada a fazer agora: {motivo}.")
            return
        restantes = IMAGENS_POR_DIA - _uso().get(_hoje_utc(), 0)
        if restantes < MINIMO_PARA_VIDEO:
            print(f"Nada a fazer agora: a cota de imagens de hoje acabou ({restantes} restantes); renova às 21:00 de Brasília.")
            return
        from robo import imagens
        imagens.LIMITE_IMAGENS = min(imagens.LIMITE_IMAGENS, restantes)
    painel.iniciar()
    import atexit
    atexit.register(_salvar_uso)
    if config.SAIDA.exists():
        shutil.rmtree(config.SAIDA)
    config.SAIDA.mkdir(parents=True)

    estudio_id = _escolher_estudio()
    estudio = config.ESTUDIOS[estudio_id]
    config.ORDEM_TEXTO = tuple(estudio["ordem_texto"])
    config.UM_PERSONAGEM_POR_CENA = estudio.get("um_personagem_por_cena", False)
    dificeis = _dificeis()
    for tentativa in (1, 2):
        recentes = {e for e, d in dificeis.get(estudio_id, {}).items()
                    if (datetime.date.today() - datetime.date.fromisoformat(d)).days <= 60}
        _excluir_especies(recentes | curriculo.DIFICEIS_IMAGEM)
        print("1/5 Roteiro"); painel.etapa("1/5 Roteiro", estudio=estudio["nome"])
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

        print("2/5 Imagens"); painel.etapa("2/5 Imagens", titulo=roteiro.get("titulo"), especie=roteiro.get("especie"))
        try:
            gerar_imagens(roteiro)
            break
        except EspecieDificil as e:
            dificeis.setdefault(estudio_id, {})[e.especie] = datetime.date.today().isoformat()
            DIFICEIS.write_text(json.dumps(dificeis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  {e}: '{e.especie}' sai do sorteio do {estudio['nome']}; nova história com outro animal")
            if tentativa == 2:
                raise
    if roteiro.get("cenas_reserva_flux"):
        cenas = ", ".join(map(str, roteiro["cenas_reserva_flux"]))
        novo = f"{roteiro['imagem_credito']} + {config.ESTUDIOS['flux']['imagem_credito']} (cenas {cenas})"
        roteiro["credito_tela"] = roteiro["credito_tela"].replace(roteiro["imagem_credito"], novo)
        roteiro["imagem_credito"] = novo

    print("3/5 Narração"); painel.etapa("3/5 Narração")
    gerar_narracao(roteiro)

    print("4/5 Montagem"); painel.etapa("4/5 Montagem", voz=roteiro.get("voz"))
    video, duracao = montar_video(roteiro)
    if duracao > 175:
        raise RuntimeError(f"Vídeo com {duracao:.0f}s passa do limite de Shorts")

    print("5/5 Publicação"); painel.etapa("5/5 Publicação")
    vid = publicar(video, roteiro, os.environ.get("PRIVACIDADE") or None)
    url = f"https://youtube.com/shorts/{vid}"
    print(f"Concluído: {url}")
    painel.concluir(roteiro["titulo"], url, voz=roteiro.get("voz"), especie=roteiro.get("especie"))

    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"## {roteiro['titulo']}\n\n- Vídeo: {url}\n- Duração: {duracao:.1f}s\n"
                    f"- Moral: {roteiro['moral']}\n")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        if not (isinstance(e, SystemExit) and not e.code):
            painel.erro(e)
        raise
