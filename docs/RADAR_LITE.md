# WRF-PALMAS Radar Lite 0.1 — teste CPU, sem NVIDIA

Este subproduto experimental gera refletividade modelada e uma aproximação da
velocidade radial a partir dos `wrfout` que o WRF-PALMAS **já produziu**. Não
compila WRF, não integra atmosfera e **não usa o motor ARHT de terceiros**. O
objetivo desta primeira versão é validar a etapa leve de radar no GitHub Actions
e em computadores com aproximadamente 8 GB de RAM.

## Testar do celular (GitHub Actions)

1. Abra `Actions` > **WRF PALMAS - Radar Lite 0.1 (CPU)**.
2. Clique `Run workflow`; deixe `source=demo` e `elevation=0.5`.
3. Baixe o artifact **WRF-PALMAS-RADAR-LITE-01** ao terminar.
4. Visualize `radar_lite_loop.gif`, os PNGs e `manifest.json`.

O modo `demo` cria uma supercélula geométrica **analítica**, sem executar o WRF:
serve apenas para testar se o pipeline funciona. Não representa previsão.

### Usar um `wrfout` existente no GitHub

Selecione `source=wrfout` e informe `source_run_id` de uma rodada do workflow
V0.6 que publicou o artifact `WRF-PALMAS-V06-WRFOUT-RAW`. Esta opção reutiliza
os NetCDF reais, sem recompilar WRF nem baixar novamente o GFS.

## Testar em PC modesto

```sh
python -m pip install numpy netCDF4 matplotlib pillow
python scripts/radar_lite.py --demo --out-dir results/radar-lite
```

Ou com NetCDF de WRF:

```sh
python scripts/radar_lite.py --run-dir /pasta/wrfout --out-dir results/radar-lite
```

CPU apenas; os campos são lidos uma camada vertical de cada vez. `--max-frames`
limita a memória usada pelo GIF. `manifest.json` registra a memória máxima do
processo em MiB no Linux e o tempo medido.

## Como o radar é aproximado

- Refletividade: lê exclusivamente `REFL_10CM` do WRF. Quando há `PH/PHB`,
  seleciona o nível de modelo mais próximo da altura do feixe para elevação
  escolhida (Terra efetiva 4/3), **na grade horizontal do WRF**.
- Velocidade: projeta U/V (depois de remover stagger) no vetor radial; corrige
  rotação de grade se `COSALPHA/SINALPHA` estiverem presentes; W vertical
  contribui se disponível; aplica aliasing com `--nyquist`.
- Sem `PH/PHB`, utiliza **máximo vertical de refletividade modelada** e não
  anuncia velocity PPI. Sem `REFL_10CM`, falha com mensagem clara.
- Não calcula polarimetria, clutter real, atenuação completa, largura do feixe,
  nem amostragem de azimute de uma antena. A resolução continua a do WRF
  (por exemplo, 9 km). Isto **não** resolve um TVS ou um tornado.

## ARHT original: checagem independente

O ZIP ARHT que foi enviado tem o backend CPU declarado, mas faltam estes dois
arquivos usados diretamente pelo seu compilador:

- `arhtmodelviewer/cpu/runtime/cuda_cpu.h`
- `arhtmodelviewer/cpu/runtime/cudacpu_rt.cpp`

Rode o diagnóstico sem executar o aplicativo original:

```sh
python scripts/arht_lite_preflight.py 'ARHT-MODEL Viewer 1.6.zip' --ram-gb 8 \
  --grid 100 --levels 30 --output preflight.json
```

O resultado indica quais arquivos faltam e uma **estimativa**, não medição, de
memória. A próxima etapa da integração do motor ARHT exige o pacote completo,
um teste do backend CPU e permissão do autor para reutilizar seu código.
O código original e seus assets **não** são enviados ao WRF-PALMAS.

## Interpretação do produto

`DEMO ANALITICA — SEM WRF`: fluxo de teste, nenhum modelo meteorológico rodou.

`WRF REFL_10CM — PRODUTO MODELADO`: saída de modelo atmosférico, não radar
observado. Campos de velocidade radial são aproximações geométricas da grade
WRF e não substituem medições Doppler.
