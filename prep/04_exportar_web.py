"""
Exporta um cubo agregado + os parametros do modelo para uma versao web
estatica (previa clicavel, sem servidor Python).

O painel cliente-a-cliente tem 216 mil linhas e nao cabe numa pagina. Mas todas
as visoes do app sao somas sobre (corte, safra, m, tipo_cliente, regiao) - entao
basta exportar esse cubo agregado e deixar a pagina somar as celulas
selecionadas. Sao ~7 mil linhas.

O simulador de safra nova tambem nao precisa da hipergeometrica no navegador:
E[X(t)] de cliente novo so depende de t, entao ficam 13 numeros por corte.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "app"))
from modelo.btyd import BGNBD                      # noqa: E402
from modelo.safras import MESES                    # noqa: E402

D = BASE / "app" / "dados"
painel = pd.read_parquet(D / "painel_safras.parquet")
meta = json.loads((D / "modelo.json").read_text(encoding="utf-8"))
elast = pd.read_parquet(D / "elasticidade_cliente.parquet")

# ---- cubo agregado --------------------------------------------------------
cubo = (painel.groupby(["corte", "safra", "m", "tipo_cliente", "regiao"],
                       observed=True)
        .agg(clientes=("Customer_ID", "nunique"),
             tr=("trans_real", "sum"), rr=("rec_real", "sum"),
             tp=("trans_prev", "sum"), rp=("rec_prev", "sum"),
             obs=("observado", "sum"))
        .reset_index())
for c in ["tr", "rr", "tp", "rp"]:
    cubo[c] = cubo[c].round(2)

cortes = sorted(cubo["corte"].unique().tolist())
safras = sorted(cubo["safra"].unique().tolist())
tipos = sorted(cubo["tipo_cliente"].unique().tolist())
regioes = sorted(cubo["regiao"].unique().tolist())
idx = {"corte": cortes, "safra": safras, "tipo": tipos, "regiao": regioes}

# linhas como arrays de inteiros/floats para o JSON ficar pequeno
linhas = [[cortes.index(r.corte), safras.index(r.safra), int(r.m),
           tipos.index(r.tipo_cliente), regioes.index(r.regiao),
           int(r.clientes), float(r.tr), float(r.rr), float(r.tp),
           float(r.rp), int(r.obs)]
          for r in cubo.itertuples()]

# ---- curva incondicional do BG/NBD por corte (para o simulador) -----------
sim = {}
for corte, m in meta["por_corte"].items():
    bg = BGNBD()
    bg.params_ = m["bgnbd"]
    sim[corte] = {
        "repeticoes": [round(float(bg.transacoes_esperadas(k + 1)), 6)
                       for k in MESES],
        "ticket_m0": round(float(m["ticket_m0_medio"]), 2),
        "ticket_recompra": round(float(m["ticket_recompra_medio"]), 2),
        "elasticidade": round(float(m["elasticidade_ticket"]), 4),
        "elasticidade_r2": round(float(m["elasticidade_r2"]), 4),
        "bgnbd": {k: round(float(v), 5) for k, v in m["bgnbd"].items()},
        "gg": {k: round(float(v), 4) for k, v in m["gamma_gamma"].items()},
        "n_clientes": m["n_clientes"],
        "pct_repetidores": round(float(m["pct_repetidores"]), 4),
        "corr": round(float(m["corr_freq_ticket"]), 4),
    }

# ---- backtest por safra (leave-one-cohort-out) ---------------------------
bt = pd.read_parquet(D / "backtest_safra.parquet")
metricas = ["rec_cliente", "freq", "ticket", "rec_total"]
bt_safras = sorted(bt["safra"].unique().tolist())
bt_origens = sorted(bt["origem"].unique().tolist())
bt_linhas = [[bt_safras.index(r.safra), int(r.origem), int(r.m),
              metricas.index(r.metrica), round(float(r.previsto), 3),
              round(float(r.realizado), 3),
              None if pd.isna(r.erro_pct) else round(float(r.erro_pct), 4)]
             for r in bt.itertuples()]

am = elast.sample(min(1200, len(elast)), random_state=7)
saida = {
    "idx": idx,
    "colunas": ["corte", "safra", "m", "tipo", "regiao", "clientes",
                "tr", "rr", "tp", "rp", "obs"],
    "linhas": linhas,
    "modelo": sim,
    "elasticidade_amostra": [[round(float(a), 2), round(float(b), 2)]
                             for a, b in zip(am["ticket_m0"],
                                             am["ticket_recompra"])],
    "fim_dados": meta["fim_dados"],
    "backtest": {
        "safras": bt_safras, "origens": bt_origens, "metricas": metricas,
        "colunas": ["safra", "origem", "m", "metrica", "previsto",
                    "realizado", "erro_pct"],
        "linhas": bt_linhas,
    },
}

alvo = BASE / "web" / "dados.json"
alvo.parent.mkdir(exist_ok=True)
alvo.write_text(json.dumps(saida, separators=(",", ":"),
                           ensure_ascii=False), encoding="utf-8")
print(f"{len(linhas):,} linhas no cubo -> {alvo} "
      f"({alvo.stat().st_size / 1024:.0f} KB)")
print("cortes:", cortes)
print("safras:", len(safras), "| tipos:", tipos, "| regioes:", regioes)
print(f"backtest: {len(bt_linhas):,} linhas, {len(bt_safras)} safras fechadas, "
      f"origens {bt_origens}")
