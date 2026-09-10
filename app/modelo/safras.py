"""
Pipeline de safras: liga o BG/NBD + Gamma-Gamma a uma visao de cohort
M0 / M1 / ... / M12, separando o que ja aconteceu do que e previsao.

Convencao de mes (a mesma da leitura de cohort do dia a dia):
    M_k = acumulado nos primeiros (k+1) meses de vida do cliente.
    M0  = o mes da aquisicao;  M3 = M0 + 3 meses seguintes;  M12 = 13 meses.

Os meses sao contados a partir do aniversario do PROPRIO cliente, nao do mes do
calendario - assim quem entrou dia 30 nao ganha um M0 de um dia so.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .btyd import BGNBD, GammaGamma, resumo_rft

UNIDADE_DIAS = 30.4375
MESES = list(range(13))          # M0 ... M12
MARCOS = [0, 3, 6, 12]           # os marcos das barras empilhadas


# --------------------------------------------------------------------------- #
def _aniversarios(data_1a: pd.Series, k: int) -> pd.Series:
    """Fim da janela M_k: data da 1a compra + (k+1) meses, menos 1 dia.
    M0 fecha no ultimo dia do 1o mes de vida do cliente."""
    return data_1a + pd.DateOffset(months=k + 1) - pd.Timedelta(days=1)


def matriz_realizada(tx: pd.DataFrame, clientes: pd.Index,
                     data_1a: pd.Series, corte: pd.Timestamp):
    """
    Devolve (transacoes, receita) acumuladas por cliente x M_k, contando apenas
    o que ocorreu ate min(aniversario_k, corte). Inclui a 1a compra.
    """
    idx = pd.Index(clientes, name="Customer_ID")
    pos = pd.Series(np.arange(len(idx)), index=idx)

    t = tx[tx["Customer_ID"].isin(idx) & (tx["data"] <= corte)]
    i = pos.reindex(t["Customer_ID"]).to_numpy()
    dias = (t["data"].to_numpy() - data_1a.reindex(idx).to_numpy()[i]
            ).astype("timedelta64[D]").astype(int)
    rec = t["receita"].to_numpy()

    n_tr = np.zeros((len(idx), len(MESES)))
    n_rc = np.zeros((len(idx), len(MESES)))
    limites = {k: (_aniversarios(data_1a.reindex(idx), k) - data_1a.reindex(idx)
                   ).dt.days.to_numpy() for k in MESES}
    for k in MESES:
        dentro = dias <= limites[k][i]
        n_tr[:, k] = np.bincount(i[dentro], minlength=len(idx))
        n_rc[:, k] = np.bincount(i[dentro], weights=rec[dentro], minlength=len(idx))
    return n_tr, n_rc, limites


# --------------------------------------------------------------------------- #
def ajustar(tx: pd.DataFrame, corte: pd.Timestamp, penalizador: float = 0.0):
    """Ajusta BG/NBD + Gamma-Gamma usando somente dados ate `corte`."""
    corte = pd.Timestamp(corte)
    rft = resumo_rft(tx, fim=corte, unidade_dias=UNIDADE_DIAS)
    rft = rft[rft["T"] > 0]                     # precisa de alguma idade

    bg = BGNBD(penalizador).fit(rft["frequencia"], rft["recencia"], rft["T"])
    gg = GammaGamma(penalizador).fit(rft["frequencia"], rft["valor_medio"])
    corr = GammaGamma.checar_independencia(rft["frequencia"], rft["valor_medio"])
    return bg, gg, rft, corr


def projetar(tx: pd.DataFrame, clientes_info: pd.DataFrame,
             corte: pd.Timestamp, bg: BGNBD, gg: GammaGamma, rft: pd.DataFrame):
    """
    Para cada cliente e cada M_k: realizado + previsto (o pedaco que ainda
    nao aconteceu ate `corte`).

    Devolve um DataFrame longo: Customer_ID, safra, tipo_cliente, regiao, m,
    trans_real, rec_real, trans_prev, rec_prev, observado.
    """
    corte = pd.Timestamp(corte)
    idx = rft.index
    info = clientes_info.set_index("Customer_ID").reindex(idx)
    data_1a = rft["data_1a"]

    n_tr, n_rc, limites = matriz_realizada(tx, idx, data_1a, corte)

    T = rft["T"].to_numpy()                     # idade no corte, em meses
    x = rft["frequencia"].to_numpy()
    t_x = rft["recencia"].to_numpy()
    ticket_cond = gg.ticket_condicional(x, rft["valor_medio"].to_numpy())

    linhas = []
    for k in MESES:
        # M_k cobre (k+1) meses de vida; T e a idade ja vivida ate o corte
        falta = np.maximum((k + 1) - T, 0.0)
        extra_tr = np.where(falta > 0,
                            bg.transacoes_condicionais(falta, x, t_x, T), 0.0)
        extra_rc = extra_tr * ticket_cond
        linhas.append(pd.DataFrame({
            "Customer_ID": idx,
            "m": k,
            "trans_real": n_tr[:, k],
            "rec_real": n_rc[:, k],
            "trans_prev": extra_tr,
            "rec_prev": extra_rc,
            "observado": falta <= 0,
        }))
    out = pd.concat(linhas, ignore_index=True)
    for c in ["safra", "tipo_cliente", "regiao"]:
        out[c] = info[c].reindex(out["Customer_ID"]).to_numpy()
    return out


# --------------------------------------------------------------------------- #
def agregar_por_safra(proj: pd.DataFrame, filtro: dict | None = None):
    """
    Agrega o painel de clientes para safra x M_k.

    Colunas de saida por safra e m:
      clientes, trans_acum, rec_acum, ticket, freq (por cliente),
      frac_observada (0 a 1: quanto do acumulado ja aconteceu de fato)
    """
    d = proj
    if filtro:
        for col, vals in filtro.items():
            if vals:
                d = d[d[col].isin(vals)]

    g = d.groupby(["safra", "m"], as_index=False).agg(
        clientes=("Customer_ID", "nunique"),
        trans_real=("trans_real", "sum"),
        rec_real=("rec_real", "sum"),
        trans_prev=("trans_prev", "sum"),
        rec_prev=("rec_prev", "sum"),
        n_obs=("observado", "sum"),
    )
    g["trans_acum"] = g["trans_real"] + g["trans_prev"]
    g["rec_acum"] = g["rec_real"] + g["rec_prev"]
    g["freq"] = g["trans_acum"] / g["clientes"]
    g["rec_cliente"] = g["rec_acum"] / g["clientes"]
    g["ticket"] = np.where(g["trans_acum"] > 0, g["rec_acum"] / g["trans_acum"], 0)
    g["frac_observada"] = g["n_obs"] / g["clientes"]
    # o mesmo, so com o realizado (usado no split escuro/claro)
    g["freq_real"] = g["trans_real"] / g["clientes"]
    g["rec_cliente_real"] = g["rec_real"] / g["clientes"]
    g["ticket_real"] = np.where(g["trans_real"] > 0,
                                g["rec_real"] / g["trans_real"], 0)
    return g


# (coluna_total, coluna_realizada, formato, e_acumulavel)
# e_acumulavel = False para metricas que nao somam entre marcos: o ticket medio
# de M12 nao e o de M0 mais um pedaco, e uma media que se move. Empilhar
# ticket seria mentira grafica, entao ele vira barra agrupada de nivel.
METRICAS = {
    "Receita por cliente": ("rec_cliente", "rec_cliente_real", "R$ {:,.0f}", True),
    "Frequência de compra": ("freq", "freq_real", "{:,.2f}", True),
    "Receita total": ("rec_acum", "rec_real", "R$ {:,.0f}", True),
    "Ticket médio": ("ticket", "ticket_real", "R$ {:,.0f}", False),
}


def segmentos_marcos(agg: pd.DataFrame, coluna: str, coluna_real: str,
                     marcos=MARCOS):
    """
    Transforma o acumulado em segmentos empilhados entre marcos:
      M0, M0->M3, M3->M6, M6->M12.
    Cada segmento vira uma linha com valor e se e realizado ou previsto.
    """
    piv = agg.pivot(index="safra", columns="m", values=coluna)
    piv_r = agg.pivot(index="safra", columns="m", values=coluna_real)
    frac = agg.pivot(index="safra", columns="m", values="frac_observada")

    linhas = []
    for safra in piv.index:
        anterior = 0.0
        for j, k in enumerate(marcos):
            valor = float(piv.loc[safra, k])
            delta = valor - anterior
            realizado = float(piv_r.loc[safra, k]) - (
                float(piv_r.loc[safra, marcos[j - 1]]) if j > 0 else 0.0)
            linhas.append({
                "safra": safra,
                "marco": f"M{k}",
                "segmento": "M0" if k == 0 else f"M{marcos[j-1]}→M{k}",
                "ordem": j,
                "valor_acum": valor,
                "delta": delta,
                "delta_realizado": max(realizado, 0.0),
                "delta_previsto": max(delta - max(realizado, 0.0), 0.0),
                "frac_observada": float(frac.loc[safra, k]),
                "tipo": "Realizado" if float(frac.loc[safra, k]) > 0.999
                        else "Previsto",
            })
            anterior = valor
    return pd.DataFrame(linhas)


# --------------------------------------------------------------------------- #
def mape_dos_paineis(painel: pd.DataFrame, corte: str, corte_verdade: str,
                     metrica: str = "rec_cliente", filtro: dict | None = None):
    """
    MAPE a partir dos paineis ja pre-calculados (sem reajustar nada).

    Compara o painel do `corte` (onde parte de M0..M12 era previsao) com o
    painel do `corte_verdade` (base cheia). So pontua celula que:
      (a) era previsao de verdade no corte  -> frac_observada < 1
      (b) ja aconteceu por inteiro na base cheia -> frac_observada = 1
    Celula ja realizada no corte nao e previsao e nao entra no MAPE.
    """
    prev = agregar_por_safra(painel[painel["corte"] == corte], filtro)
    real = agregar_por_safra(painel[painel["corte"] == corte_verdade], filtro)

    p = prev.pivot(index="safra", columns="m", values=metrica)
    r = real.pivot(index="safra", columns="m", values=metrica)
    obs_p = prev.pivot(index="safra", columns="m", values="frac_observada")
    obs_r = real.pivot(index="safra", columns="m", values="frac_observada")

    idx = p.index.intersection(r.index)
    p, r, obs_p, obs_r = p.loc[idx], r.loc[idx], obs_p.loc[idx], obs_r.loc[idx]

    valido = (obs_p < 0.999) & (obs_r > 0.999) & (r.abs() > 1e-9)
    erro_pct = (p - r) / r * 100                    # vies (com sinal)
    return (erro_pct.abs().where(valido), erro_pct.where(valido),
            p.where(valido), r.where(valido))


def mape_por_mes(painel: pd.DataFrame, verdade: str,
                 metrica: str = "rec_cliente", filtro: dict | None = None):
    """
    Erro da previsao com as safras nas linhas e os meses de vida (M0..M12) nas
    colunas - a leitura natural de cohort.

    Um corte so nao enche essa matriz: safra velha ja tinha o M12 realizado
    (nao era previsao) e safra nova ainda nao fechou (nao da para conferir).
    Aqui cada celula agrega TODOS os cortes em que aquele M_k daquela safra
    ainda era futuro e que ja fechou na base cheia - normalmente entre 1 e 9
    previsoes por celula, feitas com antecedencias diferentes.

    Devolve (mape, vies, n_cortes, melhor, pior, antecedencia_media), todos
    safra x M.
    """
    real = agregar_por_safra(painel[painel["corte"] == verdade], filtro)
    real = real.set_index(["safra", "m"])

    cortes = sorted(c for c in painel["corte"].astype(str).unique()
                    if c != verdade)
    erros = {}                                   # (safra, m) -> [(erro, antec)]
    for c in cortes:
        p = agregar_por_safra(painel[painel["corte"] == c], filtro)
        for r in p.itertuples():
            if r.frac_observada > 0.999:         # ja era realizado: nao e previsao
                continue
            chave = (r.safra, r.m)
            if chave not in real.index:
                continue
            rl = real.loc[chave]
            if rl["frac_observada"] <= 0.999:    # ainda nao fechou
                continue
            v = float(rl[metrica])
            if abs(v) < 1e-9:
                continue
            fecha = pd.Timestamp(str(r.safra) + "-01") + pd.DateOffset(months=r.m + 2)
            erros.setdefault(chave, []).append(
                ((getattr(r, metrica) - v) / v * 100,
                 (fecha - pd.Timestamp(c)).days / UNIDADE_DIAS))

    linhas = []
    for (safra, m), vals in erros.items():
        e = np.array([x[0] for x in vals])
        a = np.array([x[1] for x in vals])
        linhas.append({"safra": safra, "m": m, "mape": np.abs(e).mean(),
                       "vies": e.mean(), "n": len(e),
                       "melhor": np.abs(e).min(), "pior": np.abs(e).max(),
                       "antec": a.mean()})
    if not linhas:
        vazio = pd.DataFrame()
        return (vazio,) * 6
    d = pd.DataFrame(linhas)
    piv = lambda col: d.pivot(index="safra", columns="m", values=col).sort_index()
    return (piv("mape"), piv("vies"), piv("n"), piv("melhor"), piv("pior"),
            piv("antec"))


def mape_por_horizonte(painel: pd.DataFrame, horizonte: int, verdade: str,
                       metrica: str = "rec_cliente", filtro: dict | None = None):
    """
    Erro de previsao de UM horizonte (M3, M6 ou M12), safra por safra e corte
    por corte.

    A matriz por safra x mes de um corte so tem pouca celula pontuavel: safra
    velha ja tinha M12 realizado no corte (nao era previsao) e safra nova ainda
    nao fechou (nao da para conferir). Fixando o horizonte e varrendo os cortes,
    cada safra entra em todos os cortes em que o M_h dela ainda era futuro - o
    que enche a matriz e responde a pergunta que interessa: "com que precisao eu
    previa o M12 desta safra, e quantos meses antes".

    Devolve (erro_pct, meses_de_antecedencia, previsto, realizado), todos
    DataFrames safra x corte. erro_pct vem com sinal (+ = previu a mais).
    """
    real = agregar_por_safra(painel[painel["corte"] == verdade], filtro)
    real = real[real["m"] == horizonte].set_index("safra")
    fechadas = real.index[real["frac_observada"] > 0.999]

    cortes = [c for c in painel["corte"].astype(str).unique() if c != verdade]
    cortes = sorted(cortes)

    erro, antec, prev_v, real_v = {}, {}, {}, {}
    for c in cortes:
        p = agregar_por_safra(painel[painel["corte"] == c], filtro)
        p = p[p["m"] == horizonte].set_index("safra")
        alvo = p.index.intersection(fechadas)
        # so pontua o que ainda era previsao naquele corte
        alvo = [s for s in alvo if p.loc[s, "frac_observada"] < 0.999]
        e, a, pv, rv = {}, {}, {}, {}
        for s in alvo:
            r = float(real.loc[s, metrica])
            if abs(r) < 1e-9:
                continue
            pval = float(p.loc[s, metrica])
            e[s] = (pval - r) / r * 100
            pv[s], rv[s] = pval, r
            # quantos meses antes do fechamento do M_h esse corte foi feito
            fecha = pd.Timestamp(s + "-01") + pd.DateOffset(months=horizonte + 2)
            a[s] = round((fecha - pd.Timestamp(c)).days / UNIDADE_DIAS, 1)
        erro[c], antec[c], prev_v[c], real_v[c] = e, a, pv, rv

    mk = lambda d: pd.DataFrame(d).sort_index()
    return mk(erro), mk(antec), mk(prev_v), mk(real_v)


def backtest_mape(tx: pd.DataFrame, clientes_info: pd.DataFrame,
                  corte_calib: pd.Timestamp, fim_dados: pd.Timestamp,
                  metrica: str = "rec_cliente", filtro: dict | None = None,
                  penalizador: float = 0.0):
    """
    Ajusta so com dados ate `corte_calib`, projeta ate M12 e compara com o
    que realmente aconteceu ate `fim_dados`.

    So pontua celulas que (a) eram previsao de verdade no corte e
    (b) ja tem realizado completo na base cheia. Devolve a matriz de MAPE
    (safra x M) e o par previsto/realizado.
    """
    corte_calib, fim_dados = pd.Timestamp(corte_calib), pd.Timestamp(fim_dados)

    bg, gg, rft, _ = ajustar(tx[tx["data"] <= corte_calib], corte_calib, penalizador)
    prev = projetar(tx, clientes_info, corte_calib, bg, gg, rft)
    prev_agg = agregar_por_safra(prev, filtro)

    # verdade: mesmo painel, mas com a base inteira (nada e previsto)
    bg2, gg2, rft2, _ = ajustar(tx, fim_dados, penalizador)
    rft2 = rft2.loc[rft2.index.intersection(rft.index)]
    real = projetar(tx, clientes_info, fim_dados, bg2, gg2, rft2)
    real_agg = agregar_por_safra(real, filtro)

    p = prev_agg.pivot(index="safra", columns="m", values=metrica)
    obs_p = prev_agg.pivot(index="safra", columns="m", values="frac_observada")
    r = real_agg.pivot(index="safra", columns="m", values=metrica)
    obs_r = real_agg.pivot(index="safra", columns="m", values="frac_observada")

    idx = p.index.intersection(r.index)
    p, r, obs_p, obs_r = p.loc[idx], r.loc[idx], obs_p.loc[idx], obs_r.loc[idx]

    valido = (obs_p < 0.999) & (obs_r > 0.999) & (r.abs() > 1e-9)
    mape = (p - r).abs() / r.abs()
    mape = mape.where(valido)
    vies = (p - r) / r
    return mape * 100, vies.where(valido) * 100, p.where(valido), r.where(valido)


# --------------------------------------------------------------------------- #
def elasticidade_ticket(tx: pd.DataFrame, clientes_info: pd.DataFrame,
                        fim: pd.Timestamp):
    """
    Quanto o ticket da 1a compra diz sobre o ticket das compras seguintes.
    E a premissa que liga o slider de ticket M0 do simulador ao ticket de
    recompra previsto:

        ticket_recompra = base * (ticket_m0 / ticket_m0_base) ** beta

    beta = 1.0 -> repasse proporcional; beta = 0 -> o ticket de entrada nao
    diz nada sobre a recompra.

    Estimado no NIVEL DO CLIENTE (regressao log-log, ~4 mil pontos). No nivel
    da safra sobram ~24 medias ruidosas e o coeficiente fica instavel - a
    tabela por safra volta junto so para o grafico de checagem.
    """
    fim = pd.Timestamp(fim)
    t = tx[tx["data"] <= fim].copy()
    info = clientes_info.set_index("Customer_ID")
    t["safra"] = info["safra"].reindex(t["Customer_ID"]).to_numpy()
    t["data_1a"] = info["data_1a"].reindex(t["Customer_ID"]).to_numpy()
    t["e_primeira"] = t["data"] == t["data_1a"]

    # --- nivel cliente ---
    cli_tab = (t.groupby(["Customer_ID", "e_primeira"])["receita"].mean()
                 .unstack())
    cli_tab.columns = ["ticket_recompra", "ticket_m0"]
    cli_tab = cli_tab.dropna()
    cli_tab = cli_tab[(cli_tab > 0).all(axis=1)]

    lx = np.log(cli_tab["ticket_m0"].to_numpy())
    ly = np.log(cli_tab["ticket_recompra"].to_numpy())
    beta, alpha = np.polyfit(lx, ly, 1)
    r2 = 1 - ((ly - (alpha + beta * lx)) ** 2).sum() / ((ly - ly.mean()) ** 2).sum()

    # --- nivel safra (so para exibicao) ---
    tab = t.groupby(["safra", "e_primeira"])["receita"].mean().unstack()
    tab.columns = ["ticket_recompra", "ticket_m0"]
    tab = tab.dropna().reset_index()

    cli_tab = cli_tab.reset_index()
    cli_tab["safra"] = info["safra"].reindex(cli_tab["Customer_ID"]).to_numpy()
    return float(beta), float(r2), tab, cli_tab


def simular_safra(bg: BGNBD, gg: GammaGamma, n_clientes: int, ticket_m0: float,
                  ticket_m0_base: float, ticket_recompra_base: float,
                  elasticidade: float, meses=MESES):
    """
    Projeta uma safra que ainda nao aconteceu.

    Cliente novo nao tem historico, entao a previsao usa a forma
    incondicional do BG/NBD: transacoes acumuladas em M_k = 1 (a compra de
    aquisicao) + E[X(k)].

    Ticket: a 1a compra vale `ticket_m0` (escolhido). O ticket das compras
    seguintes parte do historico e e ajustado pela elasticidade estimada:
        ticket_recompra = base * (ticket_m0 / ticket_m0_base) ** elasticidade
    """
    meses = list(meses)
    # M_k = (k+1) meses de vida; a 1a compra e o proprio evento de aquisicao
    repet = np.array([float(bg.transacoes_esperadas(k + 1)) for k in meses])
    razao = ticket_m0 / ticket_m0_base if ticket_m0_base > 0 else 1.0
    ticket_rep = ticket_recompra_base * (razao ** elasticidade)

    trans = 1.0 + repet
    receita = ticket_m0 + repet * ticket_rep
    return pd.DataFrame({
        "m": meses,
        "clientes": n_clientes,
        "freq": trans,
        "rec_cliente": receita,
        "ticket": receita / trans,
        "rec_acum": receita * n_clientes,
        "trans_acum": trans * n_clientes,
        "ticket_recompra_previsto": ticket_rep,
    })
