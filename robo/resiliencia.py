"""Chamadas ao Gemini com fallback de modelos e espera exponencial."""
import json
import time
from types import SimpleNamespace

import requests

from google.genai import errors

TEMPORARIOS = {429, 500, 502, 503, 504}


def gerar_com_fallback(cliente, modelos, esperas, **kwargs):
    ultimo_erro = None
    for modelo in modelos:
        for tentativa, espera in enumerate([0, *esperas]):
            if espera:
                print(f"  aguardando {espera}s antes de tentar {modelo} de novo...")
                time.sleep(espera)
            try:
                resposta = cliente.models.generate_content(model=modelo, **kwargs)
                if tentativa or modelo != modelos[0]:
                    print(f"  sucesso com {modelo}")
                return resposta
            except errors.APIError as e:
                ultimo_erro = e
                codigo = getattr(e, "code", None)
                if codigo == 404:
                    print(f"  {modelo}: indisponível para esta conta (404)")
                    break
                if codigo not in TEMPORARIOS:
                    raise
                print(f"  {modelo}: erro temporário {codigo}")
                if codigo == 429 and tentativa >= 1:
                    print(f"  {modelo}: cota esgotada, passando para o próximo modelo")
                    break
        print(f"  {modelo} indisponível, passando para o próximo modelo")
    if isinstance(kwargs.get("contents"), str):
        try:
            print("  Gemini indisponível: usando reserva Cloudflare (Llama 3.3 70B)")
            return _cloudflare_texto(kwargs["contents"], kwargs.get("config"))
        except Exception as e:
            ultimo_erro = e
    raise RuntimeError(f"Todos os modelos falharam: {ultimo_erro}")


MODELO_CF_TEXTO = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def _sem_refs(schema: dict) -> dict:
    defs = schema.pop("$defs", {})

    def resolver(n):
        if isinstance(n, dict):
            if "$ref" in n:
                return resolver(dict(defs[n["$ref"].split("/")[-1]]))
            return {k: resolver(v) for k, v in n.items()}
        if isinstance(n, list):
            return [resolver(x) for x in n]
        return n
    return resolver(schema)


def _cloudflare_texto(contents: str, cfg):
    """Reserva para texto/JSON quando todos os modelos do Gemini falham."""
    from robo import config
    corpo = {
        "messages": [
            {"role": "system", "content": "Responda somente com JSON válido, em português do Brasil quando houver texto."},
            {"role": "user", "content": contents},
        ],
        "max_tokens": 4096,
        "temperature": getattr(cfg, "temperature", None) if getattr(cfg, "temperature", None) is not None else 0.7,
    }
    esquema = getattr(cfg, "response_schema", None)
    if esquema is not None and hasattr(esquema, "model_json_schema"):
        corpo["response_format"] = {"type": "json_schema", "json_schema": _sem_refs(esquema.model_json_schema())}
    url = (f"https://api.cloudflare.com/client/v4/accounts/{config.cloudflare_account()}"
           f"/ai/run/{MODELO_CF_TEXTO}")
    r = requests.post(url, headers={"Authorization": f"Bearer {config.cloudflare_token()}"},
                      json=corpo, timeout=180)
    r.raise_for_status()
    resposta = r.json()["result"]["response"]
    return SimpleNamespace(text=resposta if isinstance(resposta, str) else json.dumps(resposta, ensure_ascii=False))
