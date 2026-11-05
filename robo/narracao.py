"""Gera a narração de cada cena com o Gemini TTS (WAV 24 kHz mono)."""
import array
import json
import math
import time
import wave

from google import genai
from google.genai import types

from robo import config
from robo.resiliencia import gerar_com_fallback

TAXA, CANAIS, BYTES = 24000, 1, 2
TOM = (
    "Leia em português do Brasil, como uma contadora de histórias infantis: "
    "voz calorosa, sorridente e calma, ritmo pausado, com emoção suave. Texto: "
)


def _remover_ruido_final(pcm: bytes) -> bytes:
    """Corta o estouro de ruído que o Gemini TTS deixa no fim do áudio."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    jan = TAXA // 50  # janelas de 20 ms
    n = len(a) // jan
    if n < 10:
        return pcm
    nivel, zcr = [], []
    for k in range(n):
        seg = a[k * jan:(k + 1) * jan]
        rms = math.sqrt(sum(x * x for x in seg) / jan) or 1e-9
        nivel.append(20 * math.log10(rms / 32768))
        zcr.append(sum(1 for p, q in zip(seg, seg[1:]) if (p < 0) != (q < 0)) / jan)
    i = n - 1
    while i >= 0 and nivel[i] < -50:      # silêncio no fim
        i -= 1
    fim = i
    while i >= 0 and nivel[i] >= -50:     # trecho alto final (candidato a ruído)
        i -= 1
    ini = i + 1
    j = i
    while j >= 0 and nivel[j] < -50:      # pausa antes dele
        j -= 1
    tam, pausa = fim - ini + 1, i - j
    if 0 < tam <= 20 and pausa >= 8:
        media_db = sum(nivel[ini:fim + 1]) / tam
        media_zcr = sum(zcr[ini:fim + 1]) / tam
        if media_db > -13 and media_zcr > 0.18:   # alto e chiado: não é voz
            return a[: ini * jan].tobytes()
    return pcm


def _salvar_wav(destino, pcm: bytes) -> float:
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(CANAIS)
        w.setsampwidth(BYTES)
        w.setframerate(TAXA)
        w.writeframes(pcm)
    return len(pcm) / (TAXA * CANAIS * BYTES)


def gerar_narracao(roteiro: dict) -> list:
    pasta = config.SAIDA / "audio"
    pasta.mkdir(parents=True, exist_ok=True)
    cliente = genai.Client(api_key=config.gemini_key())
    ajustes = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.VOZ_NARRADOR)
            )
        ),
    )
    resultado = []
    for i, cena in enumerate(roteiro["cenas"], start=1):
        print(f"  narração {i}/{len(roteiro['cenas'])}...")
        resposta = gerar_com_fallback(
            cliente, config.MODELOS_VOZ, config.ESPERAS_RETRY_S,
            contents=cena["narracao"], config=ajustes,
        )
        pcm = resposta.candidates[0].content.parts[0].inline_data.data
        pcm = _remover_ruido_final(pcm)
        destino = pasta / f"cena_{i:02d}.wav"
        duracao = _salvar_wav(destino, pcm)
        resultado.append({"arquivo": destino, "duracao": duracao})
        time.sleep(20)  # respeita o limite por minuto da camada gratuita
    return resultado


if __name__ == "__main__":
    roteiro = json.loads((config.SAIDA / "roteiro.json").read_text(encoding="utf-8"))
    audios = gerar_narracao(roteiro)
    total = sum(a["duracao"] for a in audios)
    for i, a in enumerate(audios, start=1):
        print(f"  cena {i}: {a['duracao']:.1f}s")
    print(f"Total: {total:.1f}s")
