# WRF PALMAS

Modelo meteorológico regional experimental para estudos de convecção e tempo severo na América do Sul, nomeado em homenagem às vítimas do tornado de Palmas (PR) de 1959.

## Estado do projeto

**v0.1 — infraestrutura de experimentos.** Este repositório contém gerador de configurações para **WRF-ARW e WPS oficiais** e um cronômetro para executar a primeira simulação curta em computador Linux. **Não é o código-fonte do WRF e ainda não é uma previsão operacional.** Nenhuma rodada física foi executada ou validada neste repositório.

## Modo rápido

- Domínio único d01, 81 x 81 pontos, 9 km de resolução (~720 x 720 km), centrado em -27.3, -52.3 (oeste de SC / norte do RS).
- Previsão de 3 h por padrão, com opções de 6 ou 12 h. Condições iniciais e laterais de dados GFS compatíveis.
- Apenas **um** domínio, sem grade de 3 km ou 1 km nesta etapa.
- Conjunto inicial de física: Thompson, RRTMG, Noah LSM, YSU e Kain–Fritsch (a parametrização de cúmulos em 9 km é uma escolha experimental, não uma calibração sul-americana).
- Testes locais do gerador levam segundos; a integração WRF exige compilação, dados e computador adequados. **Não há garantia de rodada pronta em dezenas de minutos.**

## Primeiro passo (gera configuração, não simula)

Requer Python 3.10+.

```bash
python3 scripts/make_namelists.py --start 2026-10-13T12:00 --hours 3 \
  --geog /caminho/para/WPS_GEOG --out runs/palmas-smoke
python3 -m unittest discover -s tests -v
```

Serão gerados `namelist.wps`, `namelist.input` e `config.json` no diretório `runs/palmas-smoke`.

Para **executar fisicamente** a rodada são necessários WRF/WPS compilados, dados estáticos WPS_GEOG e GRIB2 GFS cobrindo todo o período. Veja [Guia rápido](docs/QUICKSTART.md).

## Princípios do WRF PALMAS

1. Verificação com observações, incluindo eventos severos **e dias-controle sem eventos**.
2. Diagnósticos do Hemisfério Sul calculados explicitamente (SRH, SCP, STP); não confundir sinais convencionais com erros do modelo global.
3. Arquivos de saída gerados localmente; nunca subir dados meteorológicos pesados ou binários compilados ao GitHub.
4. Melhorias de desempenho medidas (tempo real, configuração e hardware), não presumidas.

## Referências oficiais

- [WRF oficial](https://github.com/wrf-model/WRF)
- [WPS oficial](https://github.com/wrf-model/WPS)
- [Guia WPS](https://www2.mmm.ucar.edu/wrf/users/wps/WPS.html)
- [Instalação completa](https://www2.mmm.ucar.edu/wrf/site/faq/full_installation.html)

**Versão inicial: laboratório, não previsão pública nem sistema de alerta.**
