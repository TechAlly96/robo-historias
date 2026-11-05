"""Texto com reserva entre provedores: Gemini → Groq → Cloudflare (visão: só Gemini)."""
import json
import re
import time
from types import SimpleNamespace

import requests
from google.genai import errors

from robo import config

TEMPORARIOS = {429, 500, 502, 503, 504}
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELOS_GROQ = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
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


def _esquema(cfg):
    esquema = getattr(cfg, "response_schema", None)
    if esquema is not None and hasattr(esquema, "model_json_schema"):
        return _sem_refs(esquema.model_json_schema())
    return None


def _temperatura(cfg) -> float:
    t = getattr(cfg, "temperature", None)
    return 0.7 if t is None else t


def _gemini(cliente, modelos, esperas, **kwargs):
    ultimo_erro = None
    for modelo in modelos:
        for tentativa, espera in enumerate([0, *esperas]):
            if espera:
                print(f"  aguardando {espera}s antes de tentar {modelo} de novo...")
                time.sleep(espera)
            try:
                return cliente.models.generate_content(model=modelo, **kwargs), modelo
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
    raise RuntimeError(f"Gemini sem modelos disponíveis: {ultimo_erro}")


def _groq(contents: str, cfg):
    esquema = _esquema(cfg)
    cabecalho = {"Authorization": f"Bearer {config.groq_key()}"}
    ultimo = None
    for modelo in MODELOS_GROQ:
        for modo in (("json_schema", "json_object") if esquema else ("texto",)):
            sistema = "Responda somente com JSON válido que siga exatamente o esquema pedido." if esquema else ""
            if modo == "json_object":
                sistema += " Esquema JSON obrigatório: " + json.dumps(esquema, ensure_ascii=False)
            corpo = {
                "model": modelo,
                "messages": ([{"role": "system", "content": sistema}] if sistema else [])
                + [{"role": "user", "content": contents}],
                "temperature": _temperatura(cfg),
                "max_completion_tokens": 4096,
            }
            if modo == "json_schema":
                corpo["response_format"] = {"type": "json_schema", "json_schema": {"name": "resposta", "schema": esquema}}
            elif modo == "json_object":
                corpo["response_format"] = {"type": "json_object"}
            if modelo.startswith("qwen/"):
                corpo["reasoning_format"] = "hidden"
            try:
                r = requests.post(GROQ_URL, headers=cabecalho, json=corpo, timeout=120)
            except requests.RequestException as e:
                ultimo = e
                break
            if r.status_code == 200:
                texto = r.json()["choices"][0]["message"]["content"] or ""
                return re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip(), modelo
            ultimo = f"{modelo} HTTP {r.status_code}: {r.text[:200]}"
            print(f"  Groq {modelo}: HTTP {r.status_code}")
            if r.status_code == 400 and modo == "json_schema":
                continue
            break
    raise RuntimeError(f"Groq sem modelos disponíveis: {ultimo}")


def _cloudflare(contents: str, cfg):
    corpo = {
        "messages": [
            {"role": "system", "content": "Responda somente com JSON válido, em português do Brasil quando houver texto."},
            {"role": "user", "content": contents},
        ],
        "max_tokens": 4096,
        "temperature": _temperatura(cfg),
    }
    esquema = _esquema(cfg)
    if esquema:
        corpo["response_format"] = {"type": "json_schema", "json_schema": esquema}
    url = (f"https://api.cloudflare.com/client/v4/accounts/{config.cloudflare_account()}"
           f"/ai/run/{MODELO_CF_TEXTO}")
    r = requests.post(url, headers={"Authorization": f"Bearer {config.cloudflare_token()}"},
                      json=corpo, timeout=180)
    r.raise_for_status()
    resposta = r.json()["result"]["response"]
    texto = resposta if isinstance(resposta, str) else json.dumps(resposta, ensure_ascii=False)
    return texto, MODELO_CF_TEXTO


def _cloudflare_texto(contents: str, cfg):
    texto, _ = _cloudflare(contents, cfg)
    return SimpleNamespace(text=texto)


def gerar_com_fallback(cliente, modelos, esperas, ordem=None, **kwargs):
    """Tenta cada provedor na ordem. Visão (conteúdo com imagens) só no Gemini."""
    ordem = ordem or config.ORDEM_TEXTO
    contents, cfg = kwargs.get("contents"), kwargs.get("config")
    so_texto = isinstance(contents, str)
    ultimo_erro = None
    for provedor in ordem:
        if provedor != "gemini" and not so_texto:
            continue
        try:
            if provedor == "gemini":
                resp, modelo = _gemini(cliente, modelos, esperas, **kwargs)
                texto = resp.text
            elif provedor == "groq":
                texto, modelo = _groq(contents, cfg)
            elif provedor == "cloudflare":
                texto, modelo = _cloudflare(contents, cfg)
            else:
                continue
            print(f"  texto gerado por {provedor} ({modelo})")
            return SimpleNamespace(text=texto, provedor=provedor, modelo=modelo)
        except Exception as e:
            ultimo_erro = e
            print(f"  {provedor} indisponível: {str(e)[:160]}")
    raise RuntimeError(f"Todos os provedores falharam: {ultimo_erro}")
