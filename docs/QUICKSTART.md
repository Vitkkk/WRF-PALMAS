# WRF PALMAS v0.1 — primeira rodada curta

Objetivo: comprovar que WRF/WPS compilados no Linux executam uma integração meteorológica **real** sobre um domínio pequeno. Estes passos não prometem duração fixa e **não executam a simulação remotamente no GitHub**.

## 0. Preparação (uma única vez)

Instale/compile os programas oficiais **WRF-ARW** (alvo em_real, modo dmpar/MPI) e **WPS**; providencie dados estáticos WPS_GEOG. Siga o guia oficial:
https://www2.mmm.ucar.edu/wrf/site/faq/full_installation.html

Também são necessários:
- Python 3.10+, mpirun/MPI, netCDF (ncdump para conferir níveis);
- dados GRIB2 do GFS para **uma mesma inicialização** (ex.: f000 e f003 para previsão de 3 h, de 3 em 3 h);
- espaço em disco e memória livres adequados ao WRF/WPS.

Nos exemplos, substitua os caminhos por diretórios **dedicados ao projeto**. As instruções alteram o namelist.wps, Vtable e links GRIB na pasta WPS; não use uma instalação WPS ativa de outros projetos.

## 1. Configuração (segundos, sem rodar o modelo)

    git clone https://github.com/Vitkkk/WRF-PALMAS.git
    cd WRF-PALMAS
    export PALMAS_ROOT="$PWD"
    export WPS_DIR="/seu/caminho/WPS"
    export WRF_RUN="/seu/caminho/WRF/run"
    export WPS_GEOG="/seu/caminho/WPS_GEOG"
    export GFS_DIR="/seu/caminho/dados-GFS"

    python3 scripts/make_namelists.py \
       --start 2026-10-13T12:00 --hours 3 \
       --geog "$WPS_GEOG" --out runs/ensaio1

As datas UTC definem o ciclo do GFS. Os dados reais escolhidos devem ser do mesmo ciclo de inicialização, cobrir o período e conter níveis/campos meteorológicos necessários.

## 2. Preparar WPS (geogrid, ungrib, metgrid)

    cp "$PALMAS_ROOT/runs/ensaio1/namelist.wps" "$WPS_DIR/namelist.wps"
    cd "$WPS_DIR"
    ln -sfn ungrib/Variable_Tables/Vtable.GFS Vtable
    ./geogrid.exe

Verifique se "$GFS_DIR" contém os arquivos GRIB2 exigidos. Exemplo (adapte a extensão ao nome dos seus arquivos):

    ./link_grib.csh "$GFS_DIR"/*
    ./ungrib.exe
    ./metgrid.exe

O WPS deverá gerar geo_em.d01.nc e met_em.d01.<data>.nc. Se houver erros, confira os logs WPS, Vtable, origem dos dados e GEOG.

### IMPORTANTE: conferir número de níveis

**Antes do real.exe**, detecte as dimensões reais do primeiro arquivo met_em (exige ncdump) e regenere as configurações:

    cd "$PALMAS_ROOT"
    python3 scripts/make_namelists.py \
      --start 2026-10-13T12:00 --hours 3 \
      --geog "$WPS_GEOG" --out runs/ensaio1 \
      --met-em "$WPS_DIR/met_em.d01.2026-10-13_12:00:00.nc"

Os valores iniciais 34 níveis atmosféricos/4 de solo são apenas placeholders até essa verificação. Nem todo arquivo met_em tem as mesmas dimensões.

## 3. Rodar o inicializador do WRF

    cd "$WRF_RUN"
    cp "$PALMAS_ROOT/runs/ensaio1/namelist.input" namelist.input
    ln -sf "$WPS_DIR"/met_em.d01.*.nc ./
    mpirun -np 4 ./real.exe

Os arquivos **wrfinput_d01** e **wrfbdy_d01** precisam aparecer antes de iniciar wrf.exe. Confira rsl.error.0000 se a inicialização falhar. É importante usar uma cópia/pasta WRF dedicada para não substituir outros experimentos.

## 4. Cronometrar a primeira integração real

    cd "$WRF_RUN"
    bash "$PALMAS_ROOT/scripts/benchmark_wrf.sh" --check
    WRF_NP=4 PALMAS_LOG_DIR="$PALMAS_ROOT/runs/ensaio1/bench" \
      bash "$PALMAS_ROOT/scripts/benchmark_wrf.sh"

O script executa wrf.exe com MPI, procura a mensagem SUCCESS COMPLETE WRF, informa duração real e grava timings.csv. **Não executa o real.exe automaticamente**: primeiro conclua o passo 3.

Se a execução for instável, verifique os logs e considere reduzir time_step com critério. Em 9 km estamos na transição de escalas da parametrização de convecção: **não use essa configuração como referência calibrada de previsão de supercélulas/tornados**.

## 5. Evolução proposta

- v0.1: gerador de configuração, testes de formato e cronômetro (este repositório).
- v0.2: execução reprodutível em Linux com GFS de exemplo e diagnóstico de erros.
- v0.3: experimentos de 6 e 12 h, comparação de tempo por número de CPUs.
- v0.4: validação sinótica/convectiva e avaliação de parametrizações.
- v1.0 futura: aninhamento regional de 3 km, verificação observacional extensiva e pós-processamento sul-americano.

Uma saída NetCDF do WRF de 3 horas é um **teste técnico**, não uma previsão meteorológica validada. GitHub Actions aqui testa apenas a geração dos namelists, sem consumir CPU em simulações pesadas.

## Referências

- WRF/WPS: https://github.com/wrf-model/WRF e https://github.com/wrf-model/WPS
- WPS User's Guide: https://github.com/wrf-model/Users_Guide/blob/main/wps.rst
- Compilação oficial: https://www2.mmm.ucar.edu/wrf/site/faq/full_installation.html
