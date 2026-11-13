"""Gera as imagens das cenas (motor do estúdio, via Cloudflare) e confere cada uma com o Gemini (visão)."""
import base64
import io
import json
import os
import time

import requests
from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel

from robo import config
from robo.curriculo import APARENCIA
from robo.resiliencia import gerar_com_fallback

TEMPORARIOS = {429, 500, 502, 503, 504}
ESPERAS = [0, 5, 15, 45, 90]
DEFINITIVOS = {400, 401, 403, 404, 413}  # pedido/chave inválidos: repetir não adianta
RODADAS_CORRECAO = 3
# Teto de imagens por execução: ~metade da cota gratuita diária da Cloudflare (10 mil neurônios ≈ 34 imagens FLUX).
# Assim uma execução com problema nunca consome a cota do outro vídeo do dia.
LIMITE_IMAGENS = int(os.environ.get("LIMITE_IMAGENS") or 40)
_usadas = 0
COTA_ESGOTADA = False  # a Cloudflare avisou que a cota do dia acabou


class OrcamentoEsgotado(RuntimeError):
    pass


class EspecieDificil(RuntimeError):
    """A IA de imagem não consegue desenhar este animal: melhor trocar de espécie do que gastar a cota."""

    def __init__(self, especie: str):
        super().__init__(f"a IA de imagem não acertou a espécie '{especie}'")
        self.especie = especie
NEGATIVO_SDXL = ("text, letters, watermark, logo, human, person, people, realistic photo, photorealistic, "
                 "scary, violent, extra limbs, deformed, human hands, fingers, blurry")


class Veredito(BaseModel):
    cena: int
    ok: bool
    problema: str


class Verificacao(BaseModel):
    imagens: list[Veredito]


def _coadjuvantes_na_cena(roteiro: dict, cena: dict) -> list:
    txt = cena["prompt_visual"].lower()
    return [c for c in roteiro.get("coadjuvantes", [])
            if c["especie_en"].lower() in txt or c["nome"].lower() in txt]


def _prompt(roteiro: dict, cena: dict, reforco: bool = False) -> str:
    """Prompt longo e detalhado (FLUX lê o texto inteiro)."""
    especie = roteiro.get("especie_en", "")
    anatomia = APARENCIA.get(roteiro.get("especie", ""), "")
    inicio = (f"The main character is {anatomia}. " if anatomia else "")
    if reforco and especie:
        inicio = f"IMPORTANT: the main character is a {especie}, a real animal, never any other species. " + inicio
    extras = [f"{c['nome']} is a {c['especie_en']}: {c.get('aparencia_en', '')}" for c in _coadjuvantes_na_cena(roteiro, cena)]
    elenco = ("Other characters, identical in every scene: " + "; ".join(extras)
              + ". Only these characters appear; no other animals or characters, not even in the background. "
              if extras else "No other animals or characters, not even in the background. ")
    return (
        inicio
        + f"Main character, identical in every scene: {roteiro['personagem_visual']}. "
        + elenco
        + f"Scene: {cena['prompt_visual']}. "
        f"Style: {config.ESTILO_VISUAL}. "
        f"{config.PROIBIDO_VISUAL}."
    )


def _prompt_seguro(roteiro: dict, cena: dict) -> str:
    """Plano seguro para cena teimosa: close no protagonista, sem patas nem outros personagens."""
    especie = roteiro.get("especie_en", "")
    anatomia = APARENCIA.get(roteiro.get("especie", ""), f"a {especie}")
    return (
        f"Close-up portrait of the main character, {anatomia}, shown from the chest up, "
        f"paws and hands out of frame, calm happy expression, looking at the camera. "
        f"Main character details: {roteiro['personagem_visual']}. "
        f"Background setting only (no characters in it): {cena['prompt_visual']}. "
        f"Only this one character in the image, no other animals or characters. "
        f"Style: {config.ESTILO_VISUAL}. {config.PROIBIDO_VISUAL}."
    )


def _prompt_sdxl(roteiro: dict, cena: dict, reforco: bool = False) -> str:
    """Prompt curto com o essencial no começo (SDXL só lê ~77 tokens)."""
    especie = roteiro.get("especie_en", "")
    outros = ", ".join(f"a cute {c['especie_en']}" for c in _coadjuvantes_na_cena(roteiro, cena))
    visual = " ".join(roteiro["personagem_visual"].split()[:25])
    inicio = f"a {especie}, " if reforco else ""
    return (f"{inicio}cute 3D animated cartoon {especie}{' with ' + outros if outros else ''}, "
            f"{cena['prompt_visual']}, {visual}, 3D animated feature film style, soft cinematic lighting, vibrant colors")


def _para_jpeg(dados: bytes) -> bytes:
    im = Image.open(io.BytesIO(dados)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _gerar_uma(roteiro: dict, cena: dict, reforco: bool = False, seguro: bool = False) -> bytes:
    global _usadas, COTA_ESGOTADA
    if _usadas >= LIMITE_IMAGENS:
        raise OrcamentoEsgotado(f"teto de {LIMITE_IMAGENS} imagens desta execução atingido; "
                                "o restante da cota fica para o outro vídeo do dia")
    modelo = config.MODELO_IMAGEM if seguro else (roteiro.get("modelo_imagem") or config.MODELO_IMAGEM)
    if seguro:
        corpo = {"prompt": _prompt_seguro(roteiro, cena), "steps": 4}
    elif "flux" in modelo:
        corpo = {"prompt": _prompt(roteiro, cena, reforco), "steps": 4}
    else:
        corpo = {"prompt": _prompt_sdxl(roteiro, cena, reforco), "negative_prompt": NEGATIVO_SDXL,
                 "width": 1024, "height": 1024}
    url = f"https://api.cloudflare.com/client/v4/accounts/{config.cloudflare_account()}/ai/run/{modelo}"
    cabecalho = {"Authorization": f"Bearer {config.cloudflare_token()}"}
    ultimo = None
    for espera in ESPERAS:
        if espera:
            print(f"    aguardando {espera}s...")
            time.sleep(espera)
        try:
            r = requests.post(url, headers=cabecalho, json=corpo, timeout=120)
        except requests.RequestException as e:
            ultimo = e
            continue
        if r.status_code == 200:
            if "application/json" in r.headers.get("content-type", ""):
                dados = base64.b64decode(r.json()["result"]["image"])
            else:
                dados = r.content
            _usadas += 1
            return _para_jpeg(dados)
        ultimo = f"HTTP {r.status_code}: {r.text[:200]}"
        if "nsfw" in r.text.lower():
            if cena.get("_neutra"):
                break
            print("    filtro da Cloudflare recusou a descrição (falso alarme); refazendo com descrição neutra")
            neutra = dict(cena, prompt_visual="a cozy, sunny and colorful outdoor place for children", _neutra=True)
            return _gerar_uma(roteiro, neutra, reforco=reforco, seguro=True)
        if "daily free allocation" in r.text:
            COTA_ESGOTADA = True
            break  # cota diária da Cloudflare esgotada: renova às 00:00 UTC
        if r.status_code in DEFINITIVOS:
            break
    raise RuntimeError(f"Falha ao gerar imagem ({modelo}): {ultimo}")


def _verificar(roteiro: dict, caminhos: dict) -> dict:
    """Confere as imagens com o Gemini. Retorna {número da cena: problema} das reprovadas."""
    coadj = ", ".join(f"{c['nome']} = {c['especie_en']}" for c in roteiro.get("coadjuvantes", [])) or "nenhum"
    partes = [f"""Você confere as imagens de um desenho infantil antes da publicação.
Protagonista: {roteiro.get('nome_protagonista', '')} = um(a) {roteiro.get('especie', '')} ("{roteiro.get('especie_en', '')}").
Coadjuvantes: {coadj}.
Para cada imagem, reprove (ok=false) SOMENTE se houver um destes problemas:
1. o protagonista não é claramente um(a) {roteiro.get('especie_en', '')} (espécie errada, animal inventado ou híbrido); se a descrição pedida da cena mostra só um coadjuvante, é correto o protagonista não aparecer;
2. aparece qualquer animal ou personagem que não está na história, mesmo pequeno ou ao fundo, ou um coadjuvante com traços de outra espécie (ex.: orelhas de coelho num porco-espinho);
3. animal com mãos humanas e dedos, membros a mais ou deformação evidente;
4. letras, textos ou marca d'água;
5. algo assustador ou impróprio para crianças, ou pessoas/estilo fotográfico realista (o estilo deve ser 3D animado ou desenho).
Pequenas variações de roupa, cor ou cenário NÃO reprovam.
Responda uma entrada por imagem, com o número da cena e o problema (vazio se estiver ok)."""]
    for n, caminho in sorted(caminhos.items()):
        cena = roteiro["cenas"][n - 1]
        partes.append(f"Cena {n}. Narração: \"{cena['narracao']}\". Descrição pedida: {cena['prompt_visual']}")
        partes.append(types.Part.from_bytes(data=caminho.read_bytes(), mime_type="image/jpeg"))

    cliente = genai.Client(api_key=config.gemini_key())
    resp = gerar_com_fallback(
        cliente, config.MODELOS_TEXTO, config.ESPERAS_RETRY_S, contents=partes,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=Verificacao, temperature=0.0),
    )
    v = Verificacao.model_validate_json(resp.text)
    avaliadas = {x.cena for x in v.imagens}
    reprovadas = {x.cena: (x.problema or "reprovada") for x in v.imagens if not x.ok and x.cena in caminhos}
    for n in set(caminhos) - avaliadas:
        reprovadas[n] = "imagem não avaliada pelo revisor"
    return reprovadas


def gerar_imagens(roteiro: dict) -> list:
    pasta = config.SAIDA / "cenas"
    pasta.mkdir(parents=True, exist_ok=True)
    print(f"  motor de imagem: {roteiro.get('modelo_imagem') or config.MODELO_IMAGEM}")
    caminhos = {}
    for i, cena in enumerate(roteiro["cenas"], start=1):
        destino = pasta / f"cena_{i:02d}.jpg"
        print(f"  cena {i}/{len(roteiro['cenas'])}...")
        destino.write_bytes(_gerar_uma(roteiro, cena))
        caminhos[i] = destino

    pendentes = dict(caminhos)
    for rodada in range(1, RODADAS_CORRECAO + 1):
        reprovadas = _verificar(roteiro, pendentes)
        if not reprovadas:
            print(f"  verificação visual: aprovadas ({len(pendentes)} conferidas na rodada {rodada})")
            break
        especie_errada = [n for n, p in reprovadas.items() if "protagonista" in p.lower()]
        quase_tudo = rodada == 1 and len(reprovadas) >= 5
        if quase_tudo or (rodada <= 2 and len(especie_errada) >= max(3, len(pendentes) // 2 + 1)):
            for n in especie_errada:
                print(f"  cena {n} reprovada: {reprovadas[n]}")
            raise EspecieDificil(roteiro.get("especie", ""))
        pendentes = {}
        for n, problema in sorted(reprovadas.items()):
            print(f"  cena {n} reprovada: {problema} -> refazendo")
            caminhos[n].write_bytes(_gerar_uma(roteiro, roteiro["cenas"][n - 1], reforco=True))
            pendentes[n] = caminhos[n]
    else:
        reprovadas = _verificar(roteiro, pendentes)
        if reprovadas and "flux" not in (roteiro.get("modelo_imagem") or config.MODELO_IMAGEM):
            print(f"  FLUX como reserva nas cenas {sorted(reprovadas)}")
            reserva = dict(roteiro, modelo_imagem=config.MODELO_IMAGEM)
            pendentes = {}
            for n in sorted(reprovadas):
                caminhos[n].write_bytes(_gerar_uma(reserva, roteiro["cenas"][n - 1], reforco=True))
                pendentes[n] = caminhos[n]
            reprovadas = _verificar(roteiro, pendentes)
            roteiro["cenas_reserva_flux"] = sorted(set(pendentes) - set(reprovadas))
        if reprovadas and len(reprovadas) <= 2:
            print(f"  plano seguro (close no protagonista) nas cenas {sorted(reprovadas)}")
            pendentes = {}
            for n in sorted(reprovadas):
                caminhos[n].write_bytes(_gerar_uma(roteiro, roteiro["cenas"][n - 1], seguro=True))
                pendentes[n] = caminhos[n]
            reprovadas = _verificar(roteiro, pendentes)
            if "flux" not in (roteiro.get("modelo_imagem") or config.MODELO_IMAGEM):
                feitas = set(roteiro.get("cenas_reserva_flux", [])) | (set(pendentes) - set(reprovadas))
                roteiro["cenas_reserva_flux"] = sorted(feitas)
            if len(reprovadas) == 1:
                n = next(iter(reprovadas))
                vizinhas = sorted((m for m in caminhos if m != n), key=lambda m: (abs(m - n), m))
                caminhos[n].write_bytes(caminhos[vizinhas[0]].read_bytes())
                roteiro["cenas_reaproveitadas"] = {str(n): vizinhas[0]}
                print(f"  cena {n}: reaproveitada a imagem já aprovada da cena {vizinhas[0]} (mesmo personagem)")
                reprovadas = {}
        if reprovadas:
            raise RuntimeError(f"Imagens incompatíveis com a história mesmo após correções: {reprovadas}. "
                               "Nada será publicado.")
        print("  verificação visual: aprovadas após correções")
    return [caminhos[n] for n in sorted(caminhos)]


if __name__ == "__main__":
    roteiro = json.loads((config.SAIDA / "roteiro.json").read_text(encoding="utf-8"))
    imagens = gerar_imagens(roteiro)
    print(f"{len(imagens)} imagens prontas em {imagens[0].parent}")
