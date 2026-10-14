# WRF PALMAS

Modelo meteorológico regional experimental para estudos de convecção e tempo severo na América do Sul, nomeado em homenagem às vítimas do tornado de Palmas (PR) de 1959.

## Estado do projeto

**V0.4 — laboratório de supercélulas idealizadas em funcionamento.** Este repositório contém geradores de configurações WRF/WPS e workflows no GitHub Actions que já concluíram integrações ideais de supercélulas. A V0.4 adiciona mapas de W, vorticidade e refletividade de chuva aproximada em três painéis, além de uma grade ampliada. **Ainda não executa previsão operacional nem simulação regional alimentada por GFS.**


## Primeiro teste do motor: supercélula idealizada (sem GFS)

O workflow [WRF PALMAS - primeira supercelula idealizada](.github/workflows/ideal-supercell.yml) compila o **WRF 4.8.0 oficial** no GitHub Actions e tenta integrar 30 minutos meteorológicos do teste oficial **em_quarter_ss** (grade de 2 km, 42 × 42 pontos). É uma **simulação atmosférica de verdade, mas com condições idealizadas**: não representa uma previsão do Sul do Brasil.

Abra **Actions** > **WRF PALMAS - primeira supercelula idealizada** para acompanhar e, quando concluir, baixe o artifact **WRF-PALMAS-primeira-supercelula**: contém mapas de velocidade vertical W, sumário JSON, tempos de execução e logs. A compilação inicial pode levar dezenas de minutos (o guia oficial estima 10–60 min); a integração pode ser bem mais rápida.

A rotina foi concebida para começar barato e debugar a infraestrutura. A etapa seguinte usa o gerador de configuração regional de 9 km com WPS + GFS e dados reais. **Não trate os mapas idealizados como previsão ou evidência de um tornado real.**

## V0.4 — paleta de radar e painel triplo

Experimento idealizado com **122 × 122 pontos a 2 km**, **120 minutos** e mapas a cada **15 minutos**. Mostra W máximo colunar, vorticidade vertical relativa ~1 km AGL e refletividade aproximada só de chuva, em uma **paleta escalonada inspirada em radares** e com contornos de W. A execução do workflow V0.4 deve concluir antes de afirmar que os produtos estão validados.

- [Guia técnico da V0.4](docs/V04.md)
- [Workflow do modelo e artifacts](.github/workflows/ideal-supercell.yml)

## V0.3 — rotação e refletividade aproximada

O terceiro experimento idealizado estende a integração padrão para **120 minutos** (82 × 82 pontos, 2 km, saída a cada 15 minutos), com diagnósticos de **vorticidade vertical relativa perto de 1 km AGL** e **refletividade de chuva aproximada a partir de QRAIN (Kessler)**. A refletividade é uma aproximação de chuva líquida, **não radar observado nem o produto completo do WRF**. Os mapas e animações só estarão disponíveis após conclusão bem-sucedida da execução.

- [Guia da V0.3](docs/V03.md)
- [Acompanhar experimento V0.3](https://github.com/Vitkkk/WRF-PALMAS/actions/workflows/ideal-supercell.yml)

## V0.2 — animação e experimentos rápidos

A versão V0.2 já inclui renderização **de todos os horários NetCDF**, PNGs por horário, GIF e gráfico temporal de velocidade vertical, medição de memória e cache de executáveis WRF em GitHub Actions. O padrão agora é **60 min de simulação idealizada, 82 × 82 pontos a 2 km e histórico a cada 10 min**. O ensaio está sujeito a confirmação de sucesso na CI; ainda não é uma previsão baseada em observações.

- [Instruções da V0.2](docs/V02.md)
- [Executar e acompanhar a V0.2 no GitHub Actions](.github/workflows/ideal-supercell.yml)

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
