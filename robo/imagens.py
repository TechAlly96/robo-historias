"""Gera as imagens das cenas (Cloudflare FLUX) e confere cada uma com o Gemini (visão)."""
import base64
import json
import time

import requests
from google import genai
from google.genai import types
from pydantic import BaseModel

from robo import config
from robo.resiliencia import gerar_com_fallback

TEMPORARIOS = {429, 500, 502, 503, 504}
ESPERAS = [0, 5, 15, 45]
RODADAS_CORRECAO = 3


class Veredito(BaseModel):
    cena: int
    ok: bool
    problema: str


class Verificacao(BaseModel):
    imagens: list[Veredito]


def _prompt(roteiro: dict, cena: dict, reforco: bool = False) -> str:
    especie = roteiro.get("especie_en", "")
    inicio = (f"IMPORTANT: the main character is a {especie}, a real animal, never any other species. "
              if reforco and especie else "")
    return (
        inicio
        + f"Main character, identical in every scene: {roteiro['personagem_visual']}. "
        f"Scene: {cena['prompt_visual']}. "
        f"Style: {config.ESTILO_VISUAL}. "
        f"{config.PROIBIDO_VISUAL}."
    )


def _gerar_uma(prompt: str) -> bytes:
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{config.cloudflare_account()}/ai/run/{config.MODELO_IMAGEM}"
    )
    cabecalho = {"Authorization": f"Bearer {config.cloudflare_token()}"}
    ultimo = None
    for espera in ESPERAS:
        if espera:
            print(f"    aguardando {espera}s...")
            time.sleep(espera)
        try:
            r = requests.post(url, headers=cabecalho, json={"prompt": prompt, "steps": 8}, timeout=120)
        except requests.RequestException as e:
            ultimo = e
            continue
        if r.status_code == 200:
            return base64.b64decode(r.json()["result"]["image"])
        ultimo = f"HTTP {r.status_code}: {r.text[:200]}"
        if r.status_code not in TEMPORARIOS:
            break
    raise RuntimeError(f"Falha ao gerar imagem: {ultimo}")


def _verificar(roteiro: dict, caminhos: dict) -> dict:
    """Confere as imagens com o Gemini. Retorna {número da cena: problema} das reprovadas."""
    coadj = ", ".join(f"{c['nome']} = {c['especie_en']}" for c in roteiro.get("coadjuvantes", [])) or "nenhum"
    partes = [f"""Você confere as imagens de um desenho infantil antes da publicação.
Protagonista: {roteiro.get('nome_protagonista', '')} = um(a) {roteiro.get('especie', '')} ("{roteiro.get('especie_en', '')}").
Coadjuvantes: {coadj}.
Para cada imagem, reprove (ok=false) SOMENTE se houver um destes problemas:
1. o protagonista não é claramente um(a) {roteiro.get('especie_en', '')} (espécie errada, animal inventado ou híbrido);
2. aparece em destaque um animal de espécie que não está na história;
3. animal com mãos humanas e dedos, membros a mais ou deformação evidente;
4. letras, textos ou marca d'água;
5. algo assustador ou impróprio para crianças.
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
    caminhos = {}
    for i, cena in enumerate(roteiro["cenas"], start=1):
        destino = pasta / f"cena_{i:02d}.jpg"
        print(f"  cena {i}/{len(roteiro['cenas'])}...")
        destino.write_bytes(_gerar_uma(_prompt(roteiro, cena)))
        caminhos[i] = destino

    pendentes = dict(caminhos)
    for rodada in range(1, RODADAS_CORRECAO + 1):
        reprovadas = _verificar(roteiro, pendentes)
        if not reprovadas:
            print(f"  verificação visual: aprovadas ({len(pendentes)} conferidas na rodada {rodada})")
            break
        pendentes = {}
        for n, problema in sorted(reprovadas.items()):
            print(f"  cena {n} reprovada: {problema} -> refazendo")
            caminhos[n].write_bytes(_gerar_uma(_prompt(roteiro, roteiro["cenas"][n - 1], reforco=True)))
            pendentes[n] = caminhos[n]
    else:
        reprovadas = _verificar(roteiro, pendentes)
        if reprovadas:
            raise RuntimeError(f"Imagens incompatíveis com a história mesmo após correções: {reprovadas}. "
                               "Nada será publicado.")
        print("  verificação visual: aprovadas após correções")
    return [caminhos[n] for n in sorted(caminhos)]


if __name__ == "__main__":
    roteiro = json.loads((config.SAIDA / "roteiro.json").read_text(encoding="utf-8"))
    imagens = gerar_imagens(roteiro)
    print(f"{len(imagens)} imagens prontas em {imagens[0].parent}")
