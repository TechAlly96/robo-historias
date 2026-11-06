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

TENTATIVAS = 4
PALAVRAS = (85, 165)
PROIBIDO_VISUAL = ["hybrid", "crossbreed", "mixed breed", "half "]



def _ordem_revisor(autor: str) -> tuple:
    """Revisão cruzada: começa por um provedor diferente de quem escreveu."""
    outros = [p for p in config.ORDEM_TEXTO if p != autor]
    return (*outros, autor)


class Coadjuvante(BaseModel):
    nome: str
    especie_pt: str = Field(description="espécie real em português")
    especie_en: str = Field(description="a mesma espécie em inglês")
    aparencia_en: str = Field(description="aparência FIXA em inglês, 20 a 35 palavras, começando pela espécie em inglês: cores exatas do corpo e dos olhos e traços típicos da espécie")


class Cena(BaseModel):
    narracao: str = Field(description="2 frases em português do Brasil, com 15 a 20 palavras no total")
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
    cenas: list[Cena] = Field(min_length=6, max_length=8, description="exatamente 7 cenas")


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
        problemas.append(f"a narração tem {palavras} palavras; precisa ter entre 100 e 140")
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
        if _norm(co.especie_en) not in _norm(co.aparencia_en):
            problemas.append(f'a aparência de {co.nome} precisa citar a espécie "{co.especie_en}"')
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
- "personagem_visual" em inglês, com 40 a 60 palavras, começando exatamente com "a cute young {en}", com cores exatas do corpo e dos olhos, tipo de patas, asas ou nadadeiras (nunca mãos humanas), uma roupa com cores exatas e UM acessório.
- No máximo 2 coadjuvantes, todos animais reais, listados em "coadjuvantes" com a espécie em português e em inglês e uma aparência fixa em inglês ("aparencia_en") com traços típicos só da sua própria espécie.

Regras:
- EXATAMENTE 7 cenas. A narração de CADA cena tem 2 frases e 15 a 20 palavras (total de 105 a 140 palavras). Conte as cenas e as palavras antes de responder.
- Cada "prompt_visual" em inglês descreve só a ação e o ambiente da cena e cita pela espécie em inglês cada animal presente (ex.: "the {en} and the coati ..."). Nunca descreva um animal diferente do que a narração diz.
- Estrutura: apresentação, problema, tentativa, virada, solução e final feliz.
- Todo animal citado na narração ou mostrado nas imagens precisa ser o protagonista ou estar em "coadjuvantes"; não acrescente figurantes, famílias ou multidões.
- Em temas de segurança (tesoura, fogo, tomada, rua, carro), um adulto da mesma espécie do protagonista (pai, mãe ou professor, listado nos coadjuvantes) orienta e supervisiona; filhotes nunca manuseiam objeto perigoso sozinhos.
- Coadjuvantes podem ser qualquer animal real (inclusive insetos), sempre com aparência fofa e amigável, nunca assustadora.
- A história ensina sempre três coisas: CONHECIMENTO (o conteúdo escolar), SABEDORIA (a moral à luz da Bíblia) e DISCERNIMENTO: o protagonista enfrenta uma escolha clara entre o certo e o errado, pensa nas consequências e escolhe o certo, para a criança aprender a discernir.
- Revise a ortografia e a concordância de cada frase antes de responder, seguindo o Acordo Ortográfico vigente (sem trema).
- O conteúdo escolar deve ser ensinado de forma EXPLÍCITA e correta na narração: diga o fato e dê exemplos concretos (ex.: para vogais, cite cada vogal e uma palavra que começa com ela; para contar, conte os objetos em voz alta).
- Linguagem simples, frases curtas, tom acolhedor e alegre.
- Valores cristãos: amor a Deus, respeito à família e aos pais, honestidade e bondade. Deus pode ser citado com reverência, sem pregação longa.
- PROIBIDO: política, partidos ou ideologias; sexualidade, namoro ou temas de gênero; magia, bruxaria, feitiços, ocultismo ou monstros; violência, medo intenso ou morte; desrespeito aos pais; personagens, nomes ou marcas existentes (Disney, Pixar etc.).
- Não repita estes enredos já publicados: {resumos if resumos else "nenhum"}
"""
    cliente = genai.Client(api_key=config.gemini_key())
    feedback = ""
    autor = autor_id = None
    for tentativa in range(1, TENTATIVAS + 1):
        resp = gerar_com_fallback(
            cliente, config.MODELOS_TEXTO, config.ESPERAS_RETRY_S,
            ordem=(None if tentativa == 1 else _ordem_revisor(autor)),
            contents=base + feedback,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=Roteiro, temperature=0.9),
        )
        autor = autor or resp.provedor
        autor_id = autor_id or f"{resp.provedor}:{resp.modelo}"
        try:
            r = Roteiro.model_validate_json(resp.text)
            problemas = _validar(r, pt, en, chave)
        except Exception as e:
            problemas = [f"resposta fora do formato pedido ({str(e)[:200]})"]
        if not problemas:
            revisor = f"""Você é o revisor de conteúdo de um canal infantil cristão (3 a 8 anos). Reprove o roteiro em JSON abaixo se houver QUALQUER problema:
1. Coerência: narração e prompts visuais mostram exatamente os mesmos animais? O protagonista é um(a) {pt} ("{en}") em todas as cenas?
2. O conteúdo escolar ({materia}: {topico}) está correto e é ensinado com clareza?
3. A moral combina com o versículo "{texto}" ({ref}) e com valores bíblicos judaico-cristãos?
4. Está livre de política, ideologias, sexualidade, temas de gênero, magia ou ocultismo, violência, medo intenso e desrespeito à família?
5. A linguagem é adequada para crianças de 3 a 8 anos e sem erros de português?
6. A história ensina conhecimento (conteúdo escolar), sabedoria (moral bíblica) e discernimento (o protagonista escolhe com clareza entre o certo e o errado)?
Não exija menção a Deus na narração: o versículo bíblico é acrescentado automaticamente no final. Pequenas liberdades artísticas (roupas, cores, cenário) não reprovam.
Responda aprovado=true só se tudo estiver correto. Em "problemas", liste cada problema de forma objetiva.

Roteiro:
{r.model_dump_json(indent=1)}"""
            rev = Revisao.model_validate_json(gerar_com_fallback(
                cliente, config.MODELOS_TEXTO, config.ESPERAS_RETRY_S, ordem=_ordem_revisor(resp.provedor), contents=revisor,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", response_schema=Revisao, temperature=0.0),
            ).text)
            problemas = [] if rev.aprovado else (rev.problemas or ["reprovado pelo revisor sem motivo informado"])
        if not problemas:
            print(f"  roteiro aprovado na tentativa {tentativa}")
            break
        print(f"  tentativa {tentativa} reprovada: {'; '.join(problemas)[:400]}")
        feedback = ("\nATENÇÃO: a versão anterior (abaixo) foi REPROVADA por: " + "; ".join(problemas)
                    + ".\nREESCREVA essa MESMA história corrigindo TODOS os problemas, mantendo o que estava bom "
                    + "e cumprindo todas as regras acima.\nVersão anterior:\n" + resp.text[:6000] + "\n")
    else:
        raise RuntimeError("Roteiro reprovado em todas as tentativas; nada será publicado.")

    d = r.model_dump()
    d["cenas"][-1]["narracao"] = d["cenas"][-1]["narracao"].rstrip() + f" A Bíblia nos ensina: {texto} {falada}."
    final_id = f"{resp.provedor}:{resp.modelo}"
    d.update(roteirista=autor_id, editor=(final_id if final_id != autor_id else None), materia=materia, topico=topico, valor=valor, especie=pt, especie_en=en,
             versiculo={"ref": ref, "texto": texto})
    return d


if __name__ == "__main__":
    config.SAIDA.mkdir(exist_ok=True)
    r = gerar_roteiro()
    (config.SAIDA / "roteiro.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Roteirista: {r['roteirista']}")
    print(f"Título: {r['titulo']}")
    print(f"Matéria: {r['materia']} | {r['topico']}")
    print(f"Valor: {r['valor']} | {r['versiculo']['ref']}")
    print(f"Protagonista: {r['nome_protagonista']}, {r['especie']} ({r['especie_en']})")
    print(f"Coadjuvantes: {[c['nome'] + ' (' + c['especie_pt'] + ')' for c in r['coadjuvantes']]}")
    print(f"Lição: {r['licao_educativa']}")
    print(f"Moral: {r['moral']}")
    for i, c in enumerate(r["cenas"], start=1):
        print(f"  {i}. {c['narracao']}")
