"""Roteirista: currículo em rodízio, espécie fixa, versículo e revisão de conteúdo."""
import json
import random
import unicodedata

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from robo import config
from robo.curriculo import ESPECIES, MATERIAS, VALORES
from robo.resiliencia import gerar_com_fallback

TENTATIVAS = 3
PALAVRAS = (95, 140)
PROIBIDO_VISUAL = ["hybrid", "crossbreed", "mixed breed", "half "]


class Coadjuvante(BaseModel):
    nome: str
    especie_pt: str = Field(description="espécie real em português")
    especie_en: str = Field(description="a mesma espécie em inglês")


class Cena(BaseModel):
    narracao: str = Field(description="1 a 2 frases em português do Brasil")
    prompt_visual: str = Field(description="cena em INGLÊS citando pela espécie em inglês cada animal presente; sem texto na imagem")


class Roteiro(BaseModel):
    titulo: str = Field(description="até 70 caracteres, com 1 emoji no fim")
    descricao: str = Field(description="2 a 3 frases em português")
    tags: list[str] = Field(description="8 a 12 tags em português, sem #")
    nome_protagonista: str
    personagem_visual: str
    coadjuvantes: list[Coadjuvante]
    licao_educativa: str = Field(description="o conteúdo escolar ensinado, em uma frase")
    moral: str
    resumo: str = Field(description="resumo do enredo em uma frase")
    cenas: list[Cena]


class Revisao(BaseModel):
    aprovado: bool
    problemas: list[str]


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _historico() -> list:
    if config.HISTORICO.exists():
        return json.loads(config.HISTORICO.read_text(encoding="utf-8"))
    return []


def _escolher(opcoes: list, historico: list, campo: str):
    """Sorteia entre as opções usadas há mais tempo (ou nunca usadas)."""
    ultimo = {h.get(campo): i for i, h in enumerate(historico)}
    menor = min(ultimo.get(o, -1) for o in opcoes)
    return random.choice([o for o in opcoes if ultimo.get(o, -1) == menor])


def _validar(r: Roteiro, pt: str, en: str, chave: str) -> list:
    problemas = []
    if not (config.CENAS_MIN <= len(r.cenas) <= config.CENAS_MAX):
        problemas.append(f"o roteiro tem {len(r.cenas)} cenas; precisa ter entre {config.CENAS_MIN} e {config.CENAS_MAX}")
    narracao = " ".join(c.narracao for c in r.cenas)
    palavras = len(narracao.split())
    if not (PALAVRAS[0] <= palavras <= PALAVRAS[1]):
        problemas.append(f"a narração tem {palavras} palavras; precisa ter entre 100 e 130")
    if _norm(chave) not in _norm(narracao):
        problemas.append(f'a narração nunca diz que o protagonista é um(a) "{pt}"')
    if _norm(r.nome_protagonista) not in _norm(narracao):
        problemas.append("a narração não usa o nome do protagonista")
    if _norm(en) not in _norm(r.personagem_visual):
        problemas.append(f'"personagem_visual" precisa começar com "a cute young {en}"')
    visual = _norm(r.personagem_visual + " " + " ".join(c.prompt_visual for c in r.cenas))
    for termo in PROIBIDO_VISUAL:
        if termo in visual:
            problemas.append(f'proibido descrever animal híbrido ou inventado ("{termo.strip()}")')
    for co in r.coadjuvantes:
        if _norm(co.especie_en) not in visual:
            problemas.append(f'o coadjuvante {co.nome} ({co.especie_en}) não aparece pela espécie nos prompts visuais')
    return problemas


def gerar_roteiro() -> dict:
    hist = _historico()
    materia = _escolher(list(MATERIAS), hist, "materia")
    topico = _escolher(MATERIAS[materia], hist, "topico")
    valor = _escolher(list(VALORES), hist, "valor")
    refs = {v[0]: v for v in VALORES[valor]}
    ref, falada, texto = refs[_escolher(list(refs), [{"ref": h.get("versiculo", {}).get("ref")} for h in hist], "ref")]
    especies = {e[0]: e for e in ESPECIES}
    pt, en, chave = especies[_escolher(list(especies), hist, "especie")]
    resumos = [h.get("resumo") or h.get("titulo") for h in hist[-40:]]

    base = f"""Você é roteirista de um canal infantil cristão de animação 3D em português do Brasil, para crianças de 3 a 8 anos.
Crie uma fábula ORIGINAL e inédita que ensine, ao mesmo tempo:
- Conteúdo escolar: {materia}, tema "{topico}". Ensine esse conteúdo de forma correta, concreta e natural dentro da história; a criança deve aprender algo verdadeiro.
- Valor: {valor}. A moral deve combinar com este versículo, que será lido no fim: "{texto}" ({ref}). Não cite o versículo na narração; ele é acrescentado depois.

Protagonista OBRIGATÓRIO: um(a) {pt}, em inglês "{en}". Animal real, nunca híbrido nem inventado.
- Dê a ele(a) um nome brasileiro simples e use a palavra "{pt}" na narração pelo menos uma vez, para a criança saber que animal é.
- "personagem_visual" em inglês, com 40 a 60 palavras, começando exatamente com "a cute young {en}", com cores exatas do corpo, tipo de patas, asas ou nadadeiras (nunca mãos humanas), uma roupa com cores exatas e UM acessório.
- No máximo 2 coadjuvantes, todos animais reais, listados em "coadjuvantes" com a espécie em português e em inglês.

Regras:
- Entre {config.CENAS_MIN} e {config.CENAS_MAX} cenas; narração total entre 100 e 130 palavras.
- Cada "prompt_visual" em inglês descreve só a ação e o ambiente da cena e cita pela espécie em inglês cada animal presente (ex.: "the {en} and the coati ..."). Nunca descreva um animal diferente do que a narração diz.
- Estrutura: apresentação, problema, tentativa, virada, solução e final feliz.
- Linguagem simples, frases curtas, tom acolhedor e alegre.
- Valores cristãos: amor a Deus, respeito à família e aos pais, honestidade e bondade. Deus pode ser citado com reverência, sem pregação longa.
- PROIBIDO: política, partidos ou ideologias; sexualidade, namoro ou temas de gênero; magia, bruxaria, feitiços, ocultismo ou monstros; violência, medo intenso ou morte; desrespeito aos pais; personagens, nomes ou marcas existentes (Disney, Pixar etc.).
- Não repita estes enredos já publicados: {resumos if resumos else "nenhum"}
"""
    cliente = genai.Client(api_key=config.gemini_key())
    feedback = ""
    for tentativa in range(1, TENTATIVAS + 1):
        resp = gerar_com_fallback(
            cliente, config.MODELOS_TEXTO, config.ESPERAS_RETRY_S,
            contents=base + feedback,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=Roteiro, temperature=0.9),
        )
        r = Roteiro.model_validate_json(resp.text)
        problemas = _validar(r, pt, en, chave)
        if not problemas:
            revisor = f"""Você é o revisor de conteúdo de um canal infantil cristão (3 a 8 anos). Reprove o roteiro em JSON abaixo se houver QUALQUER problema:
1. Coerência: narração e prompts visuais mostram exatamente os mesmos animais? O protagonista é um(a) {pt} ("{en}") em todas as cenas?
2. O conteúdo escolar ({materia}: {topico}) está correto e é ensinado com clareza?
3. A moral combina com o versículo "{texto}" ({ref}) e com valores bíblicos judaico-cristãos?
4. Está livre de política, ideologias, sexualidade, temas de gênero, magia ou ocultismo, violência, medo intenso e desrespeito à família?
5. A linguagem é adequada para crianças de 3 a 8 anos e sem erros de português?
Responda aprovado=true só se tudo estiver correto. Em "problemas", liste cada problema de forma objetiva.

Roteiro:
{r.model_dump_json(indent=1)}"""
            rev = Revisao.model_validate_json(gerar_com_fallback(
                cliente, config.MODELOS_TEXTO, config.ESPERAS_RETRY_S, contents=revisor,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=Revisao, temperature=0.0),
            ).text)
            problemas = [] if rev.aprovado else (rev.problemas or ["reprovado pelo revisor sem motivo informado"])
        if not problemas:
            print(f"  roteiro aprovado na tentativa {tentativa}")
            break
        print(f"  tentativa {tentativa} reprovada: {'; '.join(problemas)[:400]}")
        feedback = "\nATENÇÃO: a versão anterior foi REPROVADA por: " + "; ".join(problemas) + ". Corrija tudo isso.\n"
    else:
        raise RuntimeError("Roteiro reprovado em todas as tentativas; nada será publicado.")

    d = r.model_dump()
    d["cenas"][-1]["narracao"] = d["cenas"][-1]["narracao"].rstrip() + f" A Bíblia nos ensina: {texto} {falada}."
    d.update(materia=materia, topico=topico, valor=valor, especie=pt, especie_en=en,
             versiculo={"ref": ref, "texto": texto})
    return d


if __name__ == "__main__":
    config.SAIDA.mkdir(exist_ok=True)
    r = gerar_roteiro()
    (config.SAIDA / "roteiro.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Título: {r['titulo']}")
    print(f"Matéria: {r['materia']} | {r['topico']}")
    print(f"Valor: {r['valor']} | {r['versiculo']['ref']}")
    print(f"Protagonista: {r['nome_protagonista']}, {r['especie']} ({r['especie_en']})")
    print(f"Coadjuvantes: {[c['nome'] + ' (' + c['especie_pt'] + ')' for c in r['coadjuvantes']]}")
    print(f"Lição: {r['licao_educativa']}")
    print(f"Moral: {r['moral']}")
    for i, c in enumerate(r["cenas"], start=1):
        print(f"  {i}. {c['narracao']}")
