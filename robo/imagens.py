"""Gera as imagens das cenas com Cloudflare Workers AI (FLUX)."""
import base64
import json
import time

import requests

from robo import config

TEMPORARIOS = {429, 500, 502, 503, 504}
ESPERAS = [0, 5, 15, 45]


def _prompt(roteiro: dict, cena: dict) -> str:
    return (
        f"Main character, identical in every scene: {roteiro['personagem_visual']}. "
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


def gerar_imagens(roteiro: dict) -> list:
    pasta = config.SAIDA / "cenas"
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = []
    for i, cena in enumerate(roteiro["cenas"], start=1):
        destino = pasta / f"cena_{i:02d}.jpg"
        print(f"  cena {i}/{len(roteiro['cenas'])}...")
        destino.write_bytes(_gerar_uma(_prompt(roteiro, cena)))
        caminhos.append(destino)
    return caminhos


if __name__ == "__main__":
    roteiro = json.loads((config.SAIDA / "roteiro.json").read_text(encoding="utf-8"))
    imagens = gerar_imagens(roteiro)
    print(f"{len(imagens)} imagens geradas em {imagens[0].parent}")
