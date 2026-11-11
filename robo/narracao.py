"""Narração: 1 chamada ao Gemini TTS por vídeo, dividida em cenas; Piper offline como reserva."""
import array
import base64
import io
import json
import math
import os
import subprocess
import sys
import time
import wave

import requests
from google import genai
from google.genai import errors, types

from robo import config

TAXA, CANAIS, BYTES = 24000, 1, 2
JAN = TAXA // 50                      # janelas de 20 ms
TEMPORARIOS = {429, 500, 502, 503, 504}
ESPERAS_VOZ = [10, 30]                # curtas: se a cota acabou, vai para o Piper
PIPER_VOZ = "pt_BR-faber-medium"
PIPER_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/"
PIPER_DIR = config.RAIZ / "modelos"


def _niveis(a: array.array) -> list:
    out = []
    for k in range(len(a) // JAN):
        seg = a[k * JAN:(k + 1) * JAN]
        rms = math.sqrt(sum(x * x for x in seg) / JAN) or 1e-9
        out.append(20 * math.log10(rms / 32768))
    return out


def _remover_ruido_final(pcm: bytes) -> bytes:
    """Corta o estouro de ruído que o Gemini TTS deixa no fim do áudio."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    n = len(a) // JAN
    if n < 10:
        return pcm
    nivel = _niveis(a)
    zcr = []
    for k in range(n):
        seg = a[k * JAN:(k + 1) * JAN]
        zcr.append(sum(1 for p, q in zip(seg, seg[1:]) if (p < 0) != (q < 0)) / JAN)
    i = n - 1
    while i >= 0 and nivel[i] < -50:
        i -= 1
    fim = i
    while i >= 0 and nivel[i] >= -50:
        i -= 1
    ini = i + 1
    j = i
    while j >= 0 and nivel[j] < -50:
        j -= 1
    tam, pausa = fim - ini + 1, i - j
    if 0 < tam <= 20 and pausa >= 8:
        if sum(nivel[ini:fim + 1]) / tam > -13 and sum(zcr[ini:fim + 1]) / tam > 0.18:
            return a[: ini * JAN].tobytes()
    return pcm


def _dividir(pcm: bytes, textos: list) -> list:
    """Corta a narração inteira nas pausas mais longas perto da posição esperada de cada cena."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    nivel = _niveis(a)
    n = len(nivel)
    pausas, ini = [], None
    for k, db in enumerate(nivel + [0.0]):
        if db < -45:
            ini = k if ini is None else ini
        else:
            if ini is not None and k - ini >= 6:
                pausas.append((ini, k))
            ini = None
    pesos = [len(t) for t in textos]
    total = sum(pesos)
    janela = 0.45 * n / len(textos)
    cortes, acum, anterior = [], 0, 0
    for i in range(len(textos) - 1):
        acum += pesos[i]
        esperado = n * acum / total
        candidatas = [p for p in pausas
                      if abs((p[0] + p[1]) / 2 - esperado) <= janela and (p[0] + p[1]) / 2 > anterior]
        if candidatas:
            melhor = max(candidatas, key=lambda p: p[1] - p[0])
            corte = (melhor[0] + melhor[1]) // 2
        else:
            corte = int(esperado)
            print(f"  aviso: pausa não encontrada na cena {i + 1}, corte estimado")
        cortes.append(corte)
        anterior = corte
    limites = [0, *[c * JAN for c in cortes], len(a)]
    return [a[limites[k]:limites[k + 1]].tobytes() for k in range(len(textos))]


def _salvar_wav(destino, pcm: bytes) -> float:
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(CANAIS)
        w.setsampwidth(BYTES)
        w.setframerate(TAXA)
        w.writeframes(pcm)
    return len(pcm) / (TAXA * CANAIS * BYTES)


ESTILO_VOZ = ("warm, gentle and cheerful storyteller for young children, "
              "calm pace, natural Brazilian Portuguese")
API = "https://generativelanguage.googleapis.com/v1beta"


def _pcm_de(dados) -> bytes:
    """Aceita base64, WAV ou PCM cru e devolve PCM 16 bits mono (ajusta a taxa se vier WAV)."""
    global TAXA, JAN
    if isinstance(dados, str):
        dados = base64.b64decode(dados)
    if dados[:4] == b"RIFF":
        with wave.open(io.BytesIO(dados)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise ValueError(f"áudio inesperado: {w.getnchannels()} canais, {w.getsampwidth() * 8} bits")
            TAXA = w.getframerate()
            JAN = TAXA // 50
            return w.readframes(w.getnframes())
    TAXA, JAN = 24000, 24000 // 50
    return dados


def _achar_audio(obj):
    """Procura o base64 do áudio na resposta JSON, seja qual for o formato da API."""
    if isinstance(obj, dict):
        tipo = str(obj.get("mime_type") or obj.get("mimeType") or "")
        if isinstance(obj.get("data"), str) and ("audio" in tipo or len(obj["data"]) > 2000):
            return obj["data"]
        for v in obj.values():
            achado = _achar_audio(v)
            if achado:
                return achado
    elif isinstance(obj, list):
        for v in obj:
            achado = _achar_audio(v)
            if achado:
                return achado
    return None


def _via_generate_content(modelo: str, texto: str):
    """Formato clássico (o mesmo da voz aprovada no início do canal), direto na API REST."""
    corpo = {"contents": [{"parts": [{"text": texto}]}],
             "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                 "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config.VOZ_NARRADOR}}}}}
    return requests.post(f"{API}/models/{modelo}:generateContent", json=corpo, timeout=300,
                         headers={"x-goog-api-key": config.gemini_key()})


def _via_interactions(modelo: str, texto: str):
    """Formato novo (Interactions), só para os modelos 3.8, que aceitam o estilo de leitura."""
    corpo = {"model": modelo,
             "input": [{"type": "user_input", "content": [{
                 "type": "text", "text": texto,
                 "annotations": [{"type": "speech_metadata", "style": ESTILO_VOZ}]}]}],
             "response_format": {"type": "audio"},
             "generation_config": {"speech_config": [{"voice": config.VOZ_NARRADOR}]}}
    return requests.post(f"{API}/interactions", json=corpo, timeout=300,
                         headers={"x-goog-api-key": config.gemini_key()})


def _gemini(texto: str):
    """Voz do Gemini direto pela API REST (a biblioteca google-genai mudou e quebrou a voz).
    Tenta cada modelo nos dois formatos; erro definitivo passa adiante; no fim, (None, None) = Piper."""
    for modelo in config.MODELOS_VOZ:
        caminhos = [("generateContent", _via_generate_content)]
        if "3.8" in modelo:
            caminhos.append(("interactions", _via_interactions))
        for nome, chamar in caminhos:
            for espera in [0, *ESPERAS_VOZ]:
                if espera:
                    print(f"  aguardando {espera}s ({modelo})...")
                    time.sleep(espera)
                try:
                    r = chamar(modelo, texto)
                except requests.RequestException as e:
                    print(f"  {modelo} ({nome}): falha de rede — {str(e)[:150]}")
                    continue
                if r.status_code in TEMPORARIOS:
                    print(f"  {modelo} ({nome}): erro temporário {r.status_code}")
                    continue
                if not r.ok:
                    print(f"  {modelo} ({nome}): erro {r.status_code} — {r.text[:200]}")
                    break
                try:
                    b64 = _achar_audio(r.json())
                    pcm = _pcm_de(b64) if b64 else b""
                except Exception as e:
                    print(f"  {modelo} ({nome}): resposta inesperada — {type(e).__name__}: {str(e)[:150]}")
                    break
                if len(pcm) > TAXA:  # pelo menos ~0,5 s de áudio
                    return pcm, modelo
                print(f"  {modelo} ({nome}): resposta sem áudio")
                break
    return None, None


def _piper_modelo():
    PIPER_DIR.mkdir(exist_ok=True)
    for ext in (".onnx", ".onnx.json"):
        destino = PIPER_DIR / f"{PIPER_VOZ}{ext}"
        if not destino.exists():
            print(f"  baixando voz offline {destino.name}...")
            r = requests.get(PIPER_URL + PIPER_VOZ + ext, timeout=300)
            r.raise_for_status()
            destino.write_bytes(r.content)
    return PIPER_DIR / f"{PIPER_VOZ}.onnx"


def _piper(texto: str, destino, modelo) -> float:
    subprocess.run([sys.executable, "-m", "piper", "-m", str(modelo), "-f", str(destino)],
                   input=texto.encode("utf-8"), check=True, capture_output=True)
    with wave.open(str(destino), "rb") as w:
        return w.getnframes() / w.getframerate()


def gerar_narracao(roteiro: dict) -> list:
    pasta = config.SAIDA / "audio"
    pasta.mkdir(parents=True, exist_ok=True)
    for antigo in pasta.glob("cena_*.wav"):
        antigo.unlink()
    textos = [c["narracao"].strip() for c in roteiro["cenas"]]

    pcm, modelo = (None, None)
    if os.environ.get("VOZ", "").lower() != "piper":
        try:
            pcm, modelo = _gemini("\n\n".join(textos))
        except Exception as e:  # nunca derruba o vídeo por causa da voz
            print(f"  voz Gemini falhou ({type(e).__name__}: {str(e)[:150]})")
            pcm, modelo = None, None

    resultado = []
    if pcm:
        partes = _dividir(_remover_ruido_final(pcm), textos)
        for i, parte in enumerate(partes, start=1):
            destino = pasta / f"cena_{i:02d}.wav"
            resultado.append({"arquivo": destino, "duracao": _salvar_wav(destino, _remover_ruido_final(parte))})
        print(f"  voz: {modelo} (1 chamada)")
        roteiro["voz"] = f"Gemini TTS ({modelo})"
    else:
        print("  voz Gemini indisponível: usando Piper offline")
        voz = _piper_modelo()
        for i, texto in enumerate(textos, start=1):
            destino = pasta / f"cena_{i:02d}.wav"
            resultado.append({"arquivo": destino, "duracao": _piper(texto, destino, voz)})
        print(f"  voz: Piper {PIPER_VOZ}")
        roteiro["voz"] = f"Piper ({PIPER_VOZ})"
    return resultado


if __name__ == "__main__":
    roteiro = json.loads((config.SAIDA / "roteiro.json").read_text(encoding="utf-8"))
    audios = gerar_narracao(roteiro)
    for i, a in enumerate(audios, start=1):
        print(f"  cena {i}: {a['duracao']:.1f}s")
    print(f"Total: {sum(a['duracao'] for a in audios):.1f}s")
