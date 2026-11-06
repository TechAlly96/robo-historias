"""Monta o Short vertical: zoom lento, legendas, título e trilha opcional (FFmpeg)."""
import json
import random
import re
import subprocess
import wave

from PIL import Image, ImageEnhance, ImageFilter

from robo import config

TMP = config.SAIDA / "montagem"
FOLGA_S = 0.5     # respiro depois de cada fala
ZOOM = 0.12       # intensidade do zoom por cena
FADE_S = 0.35     # transição suave entre cenas
VOLUME_MUSICA = 0.10
FPS = config.FPS
W, H = config.LARGURA, config.ALTURA
GRAVAR_LEGENDA = not config.token_tem_escopo(config.ESCOPO_LEGENDAS)  # com CC, a imagem fica limpa

CABECALHO_ASS = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,DejaVu Sans,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,2,2,70,70,300,1
Style: Titulo,DejaVu Sans,74,&H0000E1FF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,3,8,60,60,110,1
Style: Credito,DejaVu Sans,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""


def _rodar(cmd):
    subprocess.run([str(c) for c in cmd], check=True, cwd=config.RAIZ)


def _duracao_wav(caminho) -> float:
    with wave.open(str(caminho), "rb") as w:
        return w.getnframes() / w.getframerate()


def _fundo(imagem, destino):
    """Fundo vertical desfocado e escurecido, feito da própria cena."""
    im = Image.open(imagem).convert("RGB")
    escala = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * escala), round(im.height * escala)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(28))
    ImageEnhance.Brightness(im).enhance(0.75).save(destino, quality=92)


def _tempo(segundos: float) -> str:
    cs = int(round(segundos * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _limpar(texto: str) -> str:
    """Remove emojis (a fonte não tem) e caracteres especiais do ASS."""
    texto = re.sub(r"[^\u0000-\uFFFF]", "", texto).replace("\ufe0f", "")
    return texto.replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _frases(texto, duracao_fala):
    frases = [f for f in re.split(r"(?<=[.!?…])\s+", _limpar(texto)) if f]
    total = sum(len(f) for f in frases) or 1
    blocos, t = [], 0.0
    for frase in frases:
        fim = t + duracao_fala * len(frase) / total
        blocos.append((t, fim, frase))
        t = fim
    return blocos


def _legenda(destino, texto, duracao_fala, titulo=None, credito=None):
    linhas = [CABECALHO_ASS]
    blocos = _frases(texto, duracao_fala)
    if GRAVAR_LEGENDA:
        for ini, fim, frase in blocos:
            linhas.append(f"Dialogue: 0,{_tempo(ini)},{_tempo(fim)},Legenda,,0,0,0,,{frase}")
        if titulo:
            linhas.append(
                f"Dialogue: 1,{_tempo(0)},{_tempo(min(3.5, duracao_fala))},Titulo,,0,0,0,,"
                f"{{\\fad(300,400)}}{_limpar(titulo)}"
            )
    if credito:
        linhas.append(f"Dialogue: 2,{_tempo(0)},{_tempo(duracao_fala + FOLGA_S)},Credito,,0,0,0,,{_limpar(credito)}")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return blocos


def _clipe(i, imagem, audio, texto, titulo, credito=None):
    fala = _duracao_wav(audio)
    dur = fala + FOLGA_S
    quadros = max(1, round(dur * FPS))

    fundo = TMP / f"fundo_{i:02d}.jpg"
    _fundo(imagem, fundo)
    ass = TMP / f"cena_{i:02d}.ass"
    blocos = _legenda(ass, texto, fala, titulo, credito)

    z0, z1 = (1.0, 1 + ZOOM) if i % 2 else (1 + ZOOM, 1.0)
    filtro = ";".join([
        f"[1:v]scale=1620:1620,zoompan=z='{z0}+({z1 - z0:.3f})*on/{quadros}':d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1080:fps={FPS}[fg]",
        f"[0:v][fg]overlay=0:(H-h)/2-160:shortest=1,"
        f"subtitles={ass.relative_to(config.RAIZ).as_posix()},format=yuv420p,"
        f"fade=t=in:st=0:d={FADE_S},fade=t=out:st={dur - FADE_S:.3f}:d={FADE_S}[v]",
        f"[2:a]aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,"
        f"afade=t=in:st=0:d=0.05,apad,atrim=0:{dur:.3f},afade=t=out:st={dur - FADE_S:.3f}:d={FADE_S}[a]",
    ])
    saida = TMP / f"clipe_{i:02d}.mp4"
    _rodar([
        "ffmpeg", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", FPS, "-t", f"{dur:.3f}", "-i", fundo,
        "-loop", "1", "-framerate", FPS, "-t", f"{dur:.3f}", "-i", imagem,
        "-i", audio,
        "-filter_complex", filtro, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", FPS,
        "-c:a", "aac", "-b:a", "160k", "-t", f"{dur:.3f}", saida,
    ])
    return saida, dur, blocos


def montar_video(roteiro: dict):
    TMP.mkdir(parents=True, exist_ok=True)
    clipes, total, legendas = [], 0.0, []
    cenas = roteiro["cenas"]
    for i, cena in enumerate(cenas, start=1):
        print(f"  clipe {i}/{len(cenas)}...")
        clipe, dur, blocos = _clipe(
            i,
            config.SAIDA / "cenas" / f"cena_{i:02d}.jpg",
            config.SAIDA / "audio" / f"cena_{i:02d}.wav",
            cena["narracao"],
            roteiro["titulo"] if i == 1 else None,
            roteiro.get("credito_tela"),
        )
        clipes.append(clipe)
        legendas.extend([total + a, total + b, f] for a, b, f in blocos)
        total += dur

    lista = TMP / "lista.txt"
    lista.write_text("".join(f"file '{c.resolve()}'\n" for c in clipes), encoding="utf-8")
    sem_musica = TMP / "sem_musica.mp4"
    _rodar(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
            "-i", lista, "-c", "copy", sem_musica])

    (config.SAIDA / "legendas.json").write_text(json.dumps(legendas, ensure_ascii=False), encoding="utf-8")
    final = config.SAIDA / "video.mp4"
    musicas = sorted((config.ASSETS / "musicas").glob("*.mp3"))
    if musicas:
        musica = random.choice(musicas)
        print(f"  trilha: {musica.name}")
        filtro = (
            f"[1:a]volume={VOLUME_MUSICA},aresample=44100,"
            f"afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[m];"
            f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0,volume=2[a]"
        )
        _rodar(["ffmpeg", "-loglevel", "error", "-y", "-i", sem_musica,
                "-stream_loop", "-1", "-i", musica, "-filter_complex", filtro,
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                "-b:a", "160k", "-shortest", "-movflags", "+faststart", final])
    else:
        print("  sem trilha (assets/musicas vazio)")
        _rodar(["ffmpeg", "-loglevel", "error", "-y", "-i", sem_musica,
                "-c", "copy", "-movflags", "+faststart", final])
    return final, total


if __name__ == "__main__":
    roteiro = json.loads((config.SAIDA / "roteiro.json").read_text(encoding="utf-8"))
    video, duracao = montar_video(roteiro)
    print(f"Vídeo pronto: {video} | {duracao:.1f}s")
