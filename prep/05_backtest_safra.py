"""
Backtest por safra, deixando a safra de fora do ajuste (leave-one-cohort-out).

Por que este backtest existe
----------------------------
O backtest por data de corte tem um limite que a base impõe: como o BG/NBD
precisa de pelo menos 15 meses de calibracao, o primeiro corte possivel e
fev/2011. As safras que ja fecharam os 13 meses fecharam ANTES disso - entao os
primeiros meses de vida delas nunca foram "futuro" em corte nenhum, e a matriz
por corte fica com a linha pela metade.

Aqui a pergunta muda para a que interessa na pratica: "acabei de adquirir esta
safra; sabendo so o M0 dela, quanto ela vai valer ate M12?"

Para responder sem trapacear:
  1. os clientes da safra avaliada saem inteiramente do ajuste - o modelo nunca
     ve nenhuma compra deles;
  2. o modelo e ajustado no resto da base;
  3. a previsao da safra condiciona SO no que ela fez ate a origem escolhida
     (M0, M3 ou M6) - o resto e projecao;
  4. compara-se com o que a safra realmente fez, na base cheia.

Isso e validacao cruzada por safra. A ressalva honesta: o ajuste usa dados de
calendario posteriores ao periodo da safra (de outras safras), entao um choque
macro que afetasse todo mundo estaria parcialmente "conhecido". O que nao
acontece e o modelo ver a propria safra que esta prevendo.

Custo: um ajuste por safra avaliada (~4s cada).
"""
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "app"))
from modelo.btyd import BGNBD, GammaGamma, resumo_rft   # noqa: E402
from modelo.safras import MESES, UNIDADE_DIAS          # noqa: E402

FIM = pd.Timestamp("2011-11-30")
# Quanto da vida da safra o modelo pode ver antes de projetar.
#   -1  = nada. E a situacao exata do simulador de safra nova (previsao
#         incondicional) e o unico caso em que ate o M0 e previsao.
#    o  = ate o fim do M_o. Guardando TODAS as origens de 0 a 11 da para montar
#         os dois regimes de previsao a partir da mesma tabela:
#           mes a mes  -> celula (safra, k) = origem k-1, ou seja, prever o M_k
#                         com M0..M_{k-1}. E como a curva era lida na pratica.
#           de uma vez -> origem fixa, prever tudo dali ate M12 sem reancorar.
ORIGENS = [-1] + list(range(12))
SAFRA_CENSURADA = "2009-12"

tx = pd.read_parquet(BASE / "data" / "transacoes.parquet")
cli = pd.read_parquet(BASE / "data" / "clientes.parquet")
cli = cli[cli["safra"] != SAFRA_CENSURADA]
tx = tx[tx["Customer_ID"].isin(cli["Customer_ID"])]

info = cli.set_index("Customer_ID")


def fim_janela(data_1a: pd.Series, k: int) -> pd.Series:
    """Ultimo dia do M_k daquele cliente (M_k = primeiros k+1 meses de vida)."""
    return data_1a + pd.DateOffset(months=k + 1) - pd.Timedelta(days=1)


def acumulado(tx_sub, ids, data_1a, ate_k):
    """Transacoes e receita acumuladas de cada cliente ate o fim do M_{ate_k}."""
    lim = fim_janela(data_1a.reindex(ids), ate_k)
    t = tx_sub[tx_sub["Customer_ID"].isin(ids)]
    t = t[t["data"] <= t["Customer_ID"].map(lim)]
    g = t.groupby("Customer_ID")
    n = g.size().reindex(ids).fillna(0).to_numpy(float)
    r = g["receita"].sum().reindex(ids).fillna(0).to_numpy(float)
    return n, r


# Cada safra e avaliada ate onde ela ja fechou, nao ate onde a mais velha
# fechou. Para pontuar o M3 basta a safra ter o M3 fechado - exigir os 13 meses
# jogaria fora safra recente que ja tem M1, M2 e M3 medidos. O M_k de uma safra
# esta fechado quando o ULTIMO cliente dela completou k+1 meses de vida.
ultima_entrada = cli.groupby("safra")["data_1a"].max()
ate_onde = {}
for safra, d in ultima_entrada.items():
    fechados = [k for k in MESES
                if fim_janela(pd.Series([d]), k).iloc[0] <= FIM]
    if fechados:
        ate_onde[safra] = max(fechados)
avaliaveis = sorted(ate_onde)
_dist = pd.Series(ate_onde).value_counts().sort_index()
print(f"safras avaliaveis: {len(avaliaveis)}  ({avaliaveis[0]} a {avaliaveis[-1]})")
print("ate qual M cada uma fechou:")
for k, n in _dist.items():
    print(f"  M{k}: {n} safra(s)")
print(f"safras com o M12 fechado: {sum(1 for v in ate_onde.values() if v == 12)}\n")

linhas = []
for safra in avaliaveis:
    t0 = time.time()
    ids = info.index[info["safra"] == safra]

    # --- 1. ajusta SEM os clientes desta safra --------------------------------
    tx_fora = tx[~tx["Customer_ID"].isin(ids)]
    rft_fora = resumo_rft(tx_fora, fim=FIM, unidade_dias=UNIDADE_DIAS)
    rft_fora = rft_fora[rft_fora["T"] > 0]
    bg = BGNBD().fit(rft_fora["frequencia"], rft_fora["recencia"], rft_fora["T"])
    gg = GammaGamma().fit(rft_fora["frequencia"], rft_fora["valor_medio"])

    tx_safra = tx[tx["Customer_ID"].isin(ids)]
    data_1a = info.loc[ids, "data_1a"]
    n_cli = len(ids)
    k_max = ate_onde[safra]          # ultimo mes de vida ja fechado desta safra
    meses_safra = [k for k in MESES if k <= k_max]

    # --- realizado de verdade, base cheia -------------------------------------
    real_n, real_r = {}, {}
    for k in meses_safra:
        real_n[k], real_r[k] = acumulado(tx_safra, ids, data_1a, k)

    for origem in [o for o in ORIGENS if o <= k_max]:
        if origem < 0:
            # safra nova: nenhum historico. E[X(t)] incondicional, ticket
            # populacional do Gamma-Gamma. Ate o M0 vira previsao.
            ticket_pop = gg.ticket_medio_populacional()
            for k in meses_safra:
                pn = n_cli * (1.0 + float(bg.transacoes_esperadas(k + 1)))
                pr = pn * ticket_pop
                rn, rr = real_n[k].sum(), real_r[k].sum()
                pares = {
                    "rec_cliente": (pr / n_cli, rr / n_cli),
                    "rec_total": (pr, rr),
                    "freq": (pn / n_cli, rn / n_cli),
                    "ticket": (pr / max(pn, 1e-9), rr / max(rn, 1e-9)),
                }
                for met, (p_, r_) in pares.items():
                    linhas.append({
                        "safra": safra, "origem": origem, "m": k,
                        "metrica": met, "previsto": float(p_),
                        "realizado": float(r_),
                        "erro_pct": float((p_ - r_) / r_ * 100)
                                    if abs(r_) > 1e-9 else np.nan,
                        "clientes": n_cli,
                    })
            continue

        # --- 2. o que o modelo pode ver: so ate o fim do M_origem -------------
        lim = fim_janela(data_1a, origem)
        visto = tx_safra[tx_safra["data"] <= tx_safra["Customer_ID"].map(lim)]
        visto = visto.groupby(["Customer_ID", "data"], as_index=False)["receita"].sum()

        g = visto.groupby("Customer_ID")
        prim = g["data"].min().reindex(ids)
        ult = g["data"].max().reindex(ids)
        cnt = g.size().reindex(ids).fillna(0)
        x = (cnt - 1).clip(lower=0).to_numpy(float)
        t_x = ((ult - prim).dt.days / UNIDADE_DIAS).fillna(0).to_numpy(float)
        T = ((lim - data_1a).dt.days / UNIDADE_DIAS).to_numpy(float)

        rep = visto.merge(prim.rename("_1a"), left_on="Customer_ID",
                          right_index=True)
        rep = rep[rep["data"] > rep["_1a"]]
        m_x = (rep.groupby("Customer_ID")["receita"].mean()
               .reindex(ids).fillna(0).to_numpy(float))
        ticket = gg.ticket_condicional(x, m_x)

        vis_n, vis_r = acumulado(tx_safra, ids, data_1a, origem)

        for k in meses_safra:
            if k < origem:
                continue
            falta = np.maximum((k + 1) - T, 0.0)
            extra = np.where(falta > 0,
                             bg.transacoes_condicionais(falta, x, t_x, T), 0.0)
            prev_n = vis_n + extra
            prev_r = vis_r + extra * ticket

            def par(pn, pr, rn, rr):
                return {
                    "rec_cliente": (pr.sum() / n_cli, rr.sum() / n_cli),
                    "rec_total": (pr.sum(), rr.sum()),
                    "freq": (pn.sum() / n_cli, rn.sum() / n_cli),
                    "ticket": (pr.sum() / max(pn.sum(), 1e-9),
                               rr.sum() / max(rn.sum(), 1e-9)),
                }
            for met, (p_, r_) in par(prev_n, prev_r, real_n[k], real_r[k]).items():
                linhas.append({
                    "safra": safra, "origem": origem, "m": k, "metrica": met,
                    "previsto": float(p_), "realizado": float(r_),
                    "erro_pct": float((p_ - r_) / r_ * 100) if abs(r_) > 1e-9
                                else np.nan,
                    "clientes": n_cli,
                })
    print(f"{safra}  n={n_cli:>4}  fechou ate M{k_max:<2}  "
          f"r={bg.params_['r']:.3f} "
          f"alpha={bg.params_['alpha']:.3f} a={bg.params_['a']:.3f} "
          f"b={bg.params_['b']:.3f}  [{time.time()-t0:.0f}s]")

d = pd.DataFrame(linhas)
OUT = BASE / "app" / "dados"
d.to_parquet(OUT / "backtest_safra.parquet", index=False, compression="zstd")

print(f"\n{len(d):,} linhas -> backtest_safra.parquet")
mm = d[(d.metrica == "rec_cliente") & (d.origem == d.m - 1) & (d.m >= 1)]
print(f"\nmes a mes (M_k previsto com M0..M_(k-1)):")
print(f"  MAPE medio {mm.erro_pct.abs().mean():.1f}%  "
      f"| vies {mm.erro_pct.mean():+.1f}%  "
      f"| {len(mm)} previsoes em {mm.safra.nunique()} safras")
print("\n  por mes:")
for k in sorted(mm.m.unique()):
    x = mm[mm.m == k]
    print(f"    M{k:<2}: {x.erro_pct.abs().mean():5.1f}%  "
          f"({x.safra.nunique():>2} safras)")
s0 = d[(d.metrica == "rec_cliente") & (d.origem == -1)]
print(f"\nsem historico (simulador de safra nova): "
      f"MAPE {s0.erro_pct.abs().mean():.1f}%  "
      f"| M12 {s0[s0.m == 12].erro_pct.abs().mean():.1f}%")
