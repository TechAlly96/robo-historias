"""Pipeline completo: roteiro → imagens → narração → montagem → publicação."""
import json
import os
import shutil

from robo import config
from robo.imagens import gerar_imagens
from robo.montagem import montar_video
from robo.narracao import gerar_narracao
from robo.publicar import publicar
from robo.roteiro import gerar_roteiro


def main():
    if config.SAIDA.exists():
        shutil.rmtree(config.SAIDA)
    config.SAIDA.mkdir(parents=True)

    print("1/5 Roteiro")
    roteiro = gerar_roteiro()
    (config.SAIDA / "roteiro.json").write_text(
        json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {roteiro['titulo']} ({len(roteiro['cenas'])} cenas)")

    print("2/5 Imagens")
    gerar_imagens(roteiro)

    print("3/5 Narração")
    gerar_narracao(roteiro)

    print("4/5 Montagem")
    video, duracao = montar_video(roteiro)
    if duracao > 175:
        raise RuntimeError(f"Vídeo com {duracao:.0f}s passa do limite de Shorts")

    print("5/5 Publicação")
    vid = publicar(video, roteiro, os.environ.get("PRIVACIDADE") or None)
    url = f"https://youtube.com/shorts/{vid}"
    print(f"Concluído: {url}")

    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"## {roteiro['titulo']}\n\n- Vídeo: {url}\n- Duração: {duracao:.1f}s\n"
                    f"- Moral: {roteiro['moral']}\n")


if __name__ == "__main__":
    main()
