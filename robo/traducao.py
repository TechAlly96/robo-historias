"""Traduz título, descrição e frases das legendas para vários idiomas (provedores de texto com reserva)."""
import json

from google import genai
from google.genai import types
from pydantic import BaseModel

from robo import config
from robo.resiliencia import gerar_com_fallback

LOTE = 4  # idiomas por chamada


class Traducao(BaseModel):
    idioma: str
    titulo: str
    descricao: str
    frases: list[str]


class Lote(BaseModel):
    traducoes: list[Traducao]


def traduzir(titulo: str, descricao: str, frases: list, idiomas: dict) -> dict:
    cliente = genai.Client(api_key=config.gemini_key())
    resultado = {}
    codigos = list(idiomas)
    for i in range(0, len(codigos), LOTE):
        grupo = codigos[i:i + LOTE]
        prompt = f"""Traduza o conteúdo de um vídeo infantil cristão (crianças de 3 a 8 anos) do português do Brasil para estes idiomas: {', '.join(f'{c} ({idiomas[c]})' for c in grupo)}.
Regras:
- Linguagem simples, calorosa e natural para crianças em cada idioma.
- Título com no máximo 100 caracteres; mantenha o emoji e o "#Shorts".
- Na descrição, mantenha emojis, quebras de linha e hashtags; traduza o texto das hashtags quando fizer sentido.
- Versículos bíblicos: use a redação da tradução tradicional mais conhecida em cada idioma (ex.: King James em inglês, Reina-Valera em espanhol) e escreva a referência no padrão do idioma.
- Nomes dos personagens, das IAs e dos modelos não mudam.
- "frases": traduza cada frase da lista na MESMA ordem e na MESMA quantidade ({len(frases)} frases).
- Em "idioma", use exatamente o código pedido.

Título: {titulo}

Descrição:
{descricao}

Frases (JSON): {json.dumps(frases, ensure_ascii=False)}"""
        try:
            resp = gerar_com_fallback(
                cliente, config.MODELOS_TEXTO, config.ESPERAS_RETRY_S, contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=Lote, temperature=0.2),
            )
            lote = Lote.model_validate_json(resp.text)
        except Exception as e:
            print(f"  tradução falhou para {grupo}: {str(e)[:150]}")
            continue
        for t in lote.traducoes:
            if t.idioma in grupo:
                resultado[t.idioma] = {
                    "titulo": t.titulo.replace("<", "").replace(">", "")[:100],
                    "descricao": t.descricao.replace("<", "").replace(">", "")[:5000],
                    "frases": t.frases if len(t.frases) == len(frases) else None,
                }
    print(f"  traduções prontas: {', '.join(sorted(resultado)) or 'nenhuma'}")
    return resultado
