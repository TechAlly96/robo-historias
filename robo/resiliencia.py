"""Chamadas ao Gemini com fallback de modelos e espera exponencial."""
import time

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
    raise RuntimeError(f"Todos os modelos falharam: {ultimo_erro}")
