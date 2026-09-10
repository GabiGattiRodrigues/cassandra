"""
Pre-calcula os paineis de safra para cada data de corte.

O ajuste do BG/NBD leva ~10s por corte; rodar isso a cada clique no Streamlit
seria inviavel. Aqui os paineis cliente x mes ficam prontos, e o app so agrega
(instantaneo, aceita qualquer filtro) e roda o simulador em cima dos parametros
salvos - que e onde o modelo de fato "roda ao vivo".
"""
import json, pathlib, sys, time

import numpy as np
import pandas as pd

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "app"))
from modelo.safras import (ajustar, projetar, elasticidade_ticket,  # noqa: E402
                           UNIDADE_DIAS)

FIM = pd.Timestamp("2011-11-30")
# 2010-11-30 foi testado e descartado: com so 12 meses de calibracao o BG/NBD
# nao identifica o processo de churn (b estourou para ~97, ou seja, taxa de
# abandono ~0) e a projecao de M12 fica inflada. A partir de 15 meses o ajuste
# estabiliza. Fica registrado como decisao, nao como omissao.
CORTES = [d for d in pd.date_range("2011-02-28", "2011-11-30", freq="ME")]

tx = pd.read_parquet(BASE / "data" / "transacoes.parquet")
cli = pd.read_parquet(BASE / "data" / "clientes.parquet")

# --- censura a esquerda ---------------------------------------------------
# A base comeca em 01/12/2009. Quem ja era cliente antes disso aparece como se
# tivesse sido adquirido em dez/2009: a safra 2009-12 tem 951 clientes (3x a
# media) com frequencia M12 de 9,4 contra 3,9 das demais. Nao sao clientes
# novos, sao clientes antigos com historico truncado. Entram no modelo, poluem
# a distribuicao de frequencia e inflam a previsao de safra nova.
# Decisao: excluir a safra 2009-12 do ajuste e da visao.
SAFRA_CENSURADA = "2009-12"
_antes = len(cli)
cli = cli[cli["safra"] != SAFRA_CENSURADA]
tx = tx[tx["Customer_ID"].isin(cli["Customer_ID"])]
print(f"censura a esquerda: safra {SAFRA_CENSURADA} removida "
      f"({_antes - len(cli)} clientes, {(_antes-len(cli))/_antes:.1%} da base)\n")

paineis, meta = [], {}
for corte in CORTES:
    t0 = time.time()
    tx_c = tx[tx["data"] <= corte]
    bg, gg, rft, corr = ajustar(tx_c, corte)
    proj = projetar(tx, cli, corte, bg, gg, rft)
    proj["corte"] = corte.strftime("%Y-%m-%d")
    paineis.append(proj)

    # ticket medio da 1a compra e das recompras ate o corte (base do simulador)
    info = cli.set_index("Customer_ID")
    t = tx_c.copy()
    t["e_primeira"] = t["data"] == info["data_1a"].reindex(t["Customer_ID"]).to_numpy()
    tm0 = float(t.loc[t.e_primeira, "receita"].mean())
    trep = float(t.loc[~t.e_primeira, "receita"].mean())
    beta, r2, tab, _ = elasticidade_ticket(tx, cli, corte)

    meta[corte.strftime("%Y-%m-%d")] = {
        "bgnbd": {k: float(v) for k, v in bg.params_.items()},
        "gamma_gamma": {k: float(v) for k, v in gg.params_.items()},
        "log_verossimilhanca_bgnbd": float(bg.log_verossimilhanca_),
        "log_verossimilhanca_gg": float(gg.log_verossimilhanca_),
        "n_clientes": int(len(rft)),
        "corr_freq_ticket": float(corr),
        "ticket_populacional_gg": float(gg.ticket_medio_populacional()),
        "ticket_m0_medio": tm0,
        "ticket_recompra_medio": trep,
        "elasticidade_ticket": beta,
        "elasticidade_r2": r2,
        "pct_repetidores": float((rft["frequencia"] > 0).mean()),
        "freq_media_repetida": float(rft["frequencia"].mean()),
    }
    print(f"{corte.date()}  n={len(rft):>5}  "
          f"r={bg.params_['r']:.3f} alpha={bg.params_['alpha']:.3f} "
          f"a={bg.params_['a']:.3f} b={bg.params_['b']:.3f}  "
          f"corr={corr:+.3f}  elast={beta:.2f} (R2={r2:.2f})  "
          f"[{time.time()-t0:.0f}s]")

painel = pd.concat(paineis, ignore_index=True)
for c in ["safra", "tipo_cliente", "regiao", "corte"]:
    painel[c] = painel[c].astype("category")
painel["m"] = painel["m"].astype("int8")
for c in ["trans_real", "rec_real", "trans_prev", "rec_prev"]:
    painel[c] = painel[c].astype("float32")

OUT = BASE / "app" / "dados"
OUT.mkdir(parents=True, exist_ok=True)
painel.to_parquet(OUT / "painel_safras.parquet", index=False,
                  compression="zstd")
(OUT / "modelo.json").write_text(json.dumps(
    {"cortes": [c.strftime("%Y-%m-%d") for c in CORTES],
     "fim_dados": FIM.strftime("%Y-%m-%d"),
     "unidade_dias": UNIDADE_DIAS,
     "por_corte": meta}, indent=2), encoding="utf-8")

# tabelas de elasticidade (grafico de checagem do simulador)
_, _, tab_safra, tab_cli = elasticidade_ticket(tx, cli, FIM)
tab_safra.to_parquet(OUT / "elasticidade_safra.parquet", index=False)
tab_cli.sample(min(3000, len(tab_cli)), random_state=7).to_parquet(
    OUT / "elasticidade_cliente.parquet", index=False)

cli.groupby("safra").size().rename("clientes").reset_index().to_parquet(
    OUT / "safras.parquet", index=False)

print("\npainel:", painel.shape,
      f"{(OUT/'painel_safras.parquet').stat().st_size/1e6:.1f} MB")
print("ok ->", OUT)
