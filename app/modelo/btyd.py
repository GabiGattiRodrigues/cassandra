"""
BG/NBD e Gamma-Gamma implementados do zero (numpy + scipy).

Por que nao usar a lib `lifetimes`: ela esta sem manutencao desde 2020 e quebra
com versoes recentes de pandas/scipy. Aqui a matematica fica explicita, testavel
e sem dependencia fragil no deploy.

Referencias:
  Fader, Hardie & Lee (2005) - "Counting Your Customers the Easy Way:
      An Alternative to the Pareto/NBD Model"  (BG/NBD)
  Fader, Hardie & Lee (2005) - "RFM and CLV: Using Iso-Value Curves for
      Customer Base Analysis"                  (Gamma-Gamma)
"""
from __future__ import annotations

import numpy as np
from scipy import optimize
from scipy.special import gammaln, hyp2f1, logsumexp

__all__ = ["BGNBD", "GammaGamma", "resumo_rft"]


# --------------------------------------------------------------------------- #
# Preparacao: matriz RFT (recency / frequency / age) a partir de transacoes
# --------------------------------------------------------------------------- #
def resumo_rft(tx, id_col="Customer_ID", data_col="data", valor_col="receita",
               fim=None, unidade_dias=30.4375):
    """
    Converte transacoes em (frequencia, recencia, T, valor_medio) por cliente.

    Convencao BG/NBD: a 1a compra e o evento de aquisicao (nao entra em x).
      x   = numero de compras REPETIDAS
      t_x = tempo entre a 1a compra e a ULTIMA compra
      T   = tempo entre a 1a compra e o fim da janela de observacao
      m_x = ticket medio das compras repetidas

    Compras no mesmo dia contam como uma so (padrao BTYD).
    Tempo em unidades de mes (30.4375 dias) para os parametros ficarem legiveis.
    """
    import pandas as pd

    tx = tx[[id_col, data_col, valor_col]].copy()
    tx[data_col] = pd.to_datetime(tx[data_col]).dt.normalize()
    fim = pd.Timestamp(fim) if fim is not None else tx[data_col].max()
    tx = tx[tx[data_col] <= fim]

    # compras do mesmo dia viram uma so
    tx = tx.groupby([id_col, data_col], as_index=False)[valor_col].sum()

    g = tx.groupby(id_col)
    prim = g[data_col].min()
    ult = g[data_col].max()
    n = g.size()

    rep = tx.merge(prim.rename("_1a"), left_on=id_col, right_index=True)
    rep = rep[rep[data_col] > rep["_1a"]]
    m_x = rep.groupby(id_col)[valor_col].mean()

    out = pd.DataFrame({
        "frequencia": (n - 1).astype(float),
        "recencia": (ult - prim).dt.days / unidade_dias,
        "T": (fim - prim).dt.days / unidade_dias,
        "valor_medio": m_x,
        "valor_1a": g[valor_col].first(),
        "data_1a": prim,
    })
    out["valor_medio"] = out["valor_medio"].fillna(0.0)
    return out


# --------------------------------------------------------------------------- #
# BG/NBD
# --------------------------------------------------------------------------- #
class BGNBD:
    """
    Beta-Geometric / NBD.

    Compra:  taxa lambda ~ Gamma(r, alpha)
    Churn:   apos cada compra, o cliente "morre" com prob p ~ Beta(a, b)
    """

    def __init__(self, penalizador: float = 0.0):
        self.penalizador = penalizador
        self.params_: dict | None = None

    # ---- verossimilhanca ---------------------------------------------------
    @staticmethod
    def _log_verossimilhanca(params, x, t_x, T, pesos):
        r, alpha, a, b = params
        if min(params) <= 0:
            return np.inf

        ln_A1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
        ln_A2 = (gammaln(a + b) + gammaln(b + x)
                 - gammaln(b) - gammaln(a + b + x))
        ln_A3 = -(r + x) * np.log(alpha + T)
        ln_A4 = np.where(
            x > 0,
            np.log(a) - np.log(np.maximum(b + x - 1, 1e-300))
            - (r + x) * np.log(alpha + t_x),
            -np.inf,
        )
        ln_A34 = logsumexp(np.vstack([ln_A3, ln_A4]), axis=0)
        return -np.sum(pesos * (ln_A1 + ln_A2 + ln_A34))

    def fit(self, frequencia, recencia, T, pesos=None, chutes=None):
        x = np.asarray(frequencia, float)
        t_x = np.asarray(recencia, float)
        T = np.asarray(T, float)
        w = np.ones_like(x) if pesos is None else np.asarray(pesos, float)

        def objetivo(log_p):
            p = np.exp(log_p)
            nll = self._log_verossimilhanca(p, x, t_x, T, w)
            if not np.isfinite(nll):
                return 1e10
            return nll + self.penalizador * np.sum(np.asarray(log_p) ** 2)

        chutes = chutes or [(1., 1., 1., 1.), (.5, 5., .5, 5.), (2., 10., 2., 2.)]
        melhor, melhor_nll = None, np.inf
        for c in chutes:
            try:
                res = optimize.minimize(objetivo, np.log(c), method="Nelder-Mead",
                                        options={"maxiter": 4000, "xatol": 1e-6,
                                                 "fatol": 1e-6})
                res = optimize.minimize(objetivo, res.x, method="L-BFGS-B")
            except Exception:
                continue
            if res.fun < melhor_nll:
                melhor_nll, melhor = res.fun, res.x
        if melhor is None:
            raise RuntimeError("BG/NBD nao convergiu")

        r, alpha, a, b = np.exp(melhor)
        self.params_ = {"r": r, "alpha": alpha, "a": a, "b": b}
        self.log_verossimilhanca_ = -melhor_nll
        self.n_ = len(x)
        return self

    # ---- previsoes ---------------------------------------------------------
    def _p(self):
        if self.params_ is None:
            raise RuntimeError("modelo nao ajustado")
        p = self.params_
        return p["r"], p["alpha"], p["a"], p["b"]

    def transacoes_esperadas(self, t):
        """E[X(t)] - compras repetidas esperadas nos primeiros t meses de vida
        de um cliente NOVO (sem historico). Fader/Hardie eq. (9)."""
        r, alpha, a, b = self._p()
        t = np.asarray(t, float)
        hyp = hyp2f1(r, b, a + b - 1.0, t / (alpha + t))
        return (a + b - 1.0) / (a - 1.0) * (1.0 - (alpha / (alpha + t)) ** r * hyp)

    def transacoes_condicionais(self, t, frequencia, recencia, T):
        """E[Y(t) | x, t_x, T] - compras repetidas esperadas nos proximos t meses
        para um cliente COM historico. Fader/Hardie eq. (10)."""
        r, alpha, a, b = self._p()
        x = np.asarray(frequencia, float)
        t_x = np.asarray(recencia, float)
        T = np.asarray(T, float)
        t = np.asarray(t, float)

        primeiro = (a + b + x - 1.0) / (a - 1.0)
        hyp = hyp2f1(r + x, b + x, a + b + x - 1.0, t / (alpha + T + t))
        num = primeiro * (1.0 - ((alpha + T) / (alpha + T + t)) ** (r + x) * hyp)

        ln_A3 = -(r + x) * np.log(alpha + T)
        ln_A4 = np.where(x > 0,
                         np.log(a) - np.log(np.maximum(b + x - 1, 1e-300))
                         - (r + x) * np.log(alpha + t_x),
                         -np.inf)
        den = 1.0 + np.where(x > 0, np.exp(ln_A4 - ln_A3), 0.0)
        return num / den

    def prob_vivo(self, frequencia, recencia, T):
        """P(cliente ainda ativo | x, t_x, T)."""
        r, alpha, a, b = self._p()
        x = np.asarray(frequencia, float)
        t_x = np.asarray(recencia, float)
        T = np.asarray(T, float)
        log_div = np.where(x > 0,
                           np.log(a) - np.log(np.maximum(b + x - 1, 1e-300))
                           + (r + x) * (np.log(alpha + T) - np.log(alpha + t_x)),
                           -np.inf)
        return 1.0 / (1.0 + np.exp(log_div))


# --------------------------------------------------------------------------- #
# Gamma-Gamma
# --------------------------------------------------------------------------- #
class GammaGamma:
    """
    Valor monetario: ticket individual ~ Gamma(p, nu_i), nu_i ~ Gamma(q, v).
    Assume independencia entre frequencia e ticket - a checagem dessa hipotese
    esta em `checar_independencia`.
    """

    def __init__(self, penalizador: float = 0.0):
        self.penalizador = penalizador
        self.params_: dict | None = None

    @staticmethod
    def _log_verossimilhanca(params, x, m_x):
        p, q, v = params
        if min(params) <= 0:
            return np.inf
        return -np.sum(
            gammaln(p * x + q) - gammaln(p * x) - gammaln(q)
            + q * np.log(v) + (p * x - 1) * np.log(m_x) + (p * x) * np.log(x)
            - (p * x + q) * np.log(v + m_x * x)
        )

    def fit(self, frequencia, valor_medio, chutes=None):
        x = np.asarray(frequencia, float)
        m = np.asarray(valor_medio, float)
        mask = (x > 0) & (m > 0)
        x, m = x[mask], m[mask]

        def objetivo(log_p):
            nll = self._log_verossimilhanca(np.exp(log_p), x, m)
            if not np.isfinite(nll):
                return 1e12
            return nll + self.penalizador * np.sum(np.asarray(log_p) ** 2)

        chutes = chutes or [(1., 1., 1.), (6., 4., 15.), (2., 10., 100.)]
        melhor, melhor_nll = None, np.inf
        for c in chutes:
            try:
                res = optimize.minimize(objetivo, np.log(c), method="Nelder-Mead",
                                        options={"maxiter": 4000})
                res = optimize.minimize(objetivo, res.x, method="L-BFGS-B")
            except Exception:
                continue
            if res.fun < melhor_nll:
                melhor_nll, melhor = res.fun, res.x
        if melhor is None:
            raise RuntimeError("Gamma-Gamma nao convergiu")

        p, q, v = np.exp(melhor)
        self.params_ = {"p": p, "q": q, "v": v}
        self.log_verossimilhanca_ = -melhor_nll
        self.n_ = len(x)
        return self

    def ticket_medio_populacional(self):
        p, q, v = (self.params_[k] for k in "pqv")
        return p * v / (q - 1.0)

    def ticket_condicional(self, frequencia, valor_medio):
        """E[M | x, m_x] - media ponderada entre o ticket do cliente e o da
        populacao; quem tem pouco historico e puxado para a media."""
        p, q, v = (self.params_[k] for k in "pqv")
        x = np.asarray(frequencia, float)
        m = np.asarray(valor_medio, float)
        pop = p * v / (q - 1.0)
        peso_ind = (p * x) / (p * x + q - 1.0)
        return np.where(x > 0, peso_ind * m + (1 - peso_ind) * pop, pop)

    @staticmethod
    def checar_independencia(frequencia, valor_medio):
        """Correlacao de Pearson entre frequencia e ticket entre os clientes com
        recompra. |r| < 0.1 e o criterio usual para aceitar a hipotese."""
        x = np.asarray(frequencia, float)
        m = np.asarray(valor_medio, float)
        mask = (x > 0) & (m > 0)
        if mask.sum() < 3:
            return np.nan
        return float(np.corrcoef(x[mask], m[mask])[0, 1])
