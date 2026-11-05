"""Gera o roteiro da história com o Gemini (saída JSON validada)."""
import json
import random

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from robo import config
from robo.resiliencia import gerar_com_fallback

TEMAS = [
    "amizade", "coragem", "honestidade", "gentileza", "paciência",
    "trabalho em equipe", "respeito às diferenças", "gratidão",
    "cuidar da natureza", "perseverança", "compartilhar", "pedir desculpas",
    "superar o medo", "ajudar quem precisa", "curiosidade e aprendizado",
]
CENARIOS = [
    "floresta encantada", "fundo do mar", "fazenda", "montanhas nevadas",
    "cidade de brinquedos", "jardim florido", "selva tropical", "deserto",
    "lago ao entardecer", "vila de cogumelos", "céu entre nuvens", "rio cristalino",
]


class Cena(BaseModel):
    narracao: str = Field(description="1 a 2 frases em português do Brasil, narradas em voz alta")
    prompt_visual: str = Field(description="Descrição visual da cena em INGLÊS, sem texto na imagem")


class Roteiro(BaseModel):
    titulo: str = Field(description="Título do vídeo, até 70 caracteres, com 1 emoji no fim")
    descricao: str = Field(description="Descrição do vídeo em 2 a 3 frases, em português")
    tags: list[str] = Field(description="8 a 12 tags em português, sem #")
    personagem_visual: str = Field(description="Ficha visual FIXA do protagonista em INGLÊS: espécie, cores, roupa, acessório")
    moral: str = Field(description="Lição de moral em uma frase curta")
    cenas: list[Cena]


def _titulos_anteriores(limite: int = 40) -> list[str]:
    if not config.HISTORICO.exists():
        return []
    dados = json.loads(config.HISTORICO.read_text(encoding="utf-8"))
    return [d["titulo"] for d in dados[-limite:]]


def gerar_roteiro() -> Roteiro:
    tema = random.choice(TEMAS)
    cenario = random.choice(CENARIOS)
    anteriores = _titulos_anteriores()

    instrucao = f"""Você é roteirista de um canal infantil de animação 3D em português do Brasil.
Crie uma fábula ORIGINAL, curta, acolhedora e adequada para crianças de 3 a 8 anos.

Regras:
- Tema: {tema}. Cenário principal: {cenario}.
- Protagonista: um animal fofo e original, com nome brasileiro simples e fácil de lembrar.
- Exatamente entre {config.CENAS_MIN} e {config.CENAS_MAX} cenas.
- Narração total entre 110 e 150 palavras (cerca de {config.DURACAO_ALVO_S[0]} a {config.DURACAO_ALVO_S[1]} segundos).
- Estrutura: apresentação, problema, tentativa, virada, solução e final feliz com a moral.
- Linguagem simples, frases curtas, sem violência, medo intenso ou temas adultos.
- PROIBIDO usar personagens, nomes ou marcas existentes (Disney, Pixar, DreamWorks etc).
- "personagem_visual" é a aparência fixa do protagonista em inglês, com 40 a 60 palavras, sempre com: espécie, cor exata do pelo/penas e manchas, cor e formato do topete ou cabelo, formato de chifres/orelhas, tipo de patas (hooves/paws/claws, NUNCA mãos humanas), roupa com cores exatas e UM único acessório. Use cores fixas e específicas (ex.: "orange tuft", nunca "light hair").
- Cada "prompt_visual" descreve só a ação e o ambiente da cena, em inglês, sem repetir a ficha do personagem.
- Não repita estas histórias anteriores: {anteriores if anteriores else "nenhuma"}.
"""

    cliente = genai.Client(api_key=config.gemini_key())
    resposta = gerar_com_fallback(
        cliente, config.MODELOS_TEXTO, config.ESPERAS_RETRY_S,
        contents=instrucao,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Roteiro,
            temperature=1.0,
        ),
    )
    roteiro = Roteiro.model_validate_json(resposta.text)

    if not (config.CENAS_MIN <= len(roteiro.cenas) <= config.CENAS_MAX):
        raise ValueError(f"Roteiro com {len(roteiro.cenas)} cenas, fora do intervalo")
    return roteiro


if __name__ == "__main__":
    config.SAIDA.mkdir(exist_ok=True)
    r = gerar_roteiro()
    destino = config.SAIDA / "roteiro.json"
    destino.write_text(r.model_dump_json(indent=2), encoding="utf-8")
    palavras = sum(len(c.narracao.split()) for c in r.cenas)
    print(f"Título: {r.titulo}")
    print(f"Cenas: {len(r.cenas)} | Palavras: {palavras} | Moral: {r.moral}")
    print(f"Salvo em {destino}")
