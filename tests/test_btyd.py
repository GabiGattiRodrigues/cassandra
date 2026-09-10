"""
Validacao do BG/NBD e do Gamma-Gamma por recuperacao de parametros:
simula dados a partir do processo gerador com parametros conhecidos e checa
se o ajuste volta nos mesmos numeros e se as formulas fechadas batem com
a media da simulacao.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "app"))

import numpy as np
from modelo.btyd import BGNBD, GammaGamma

RNG = np.random.default_rng(42)


def simular_bgnbd(n, r, alpha, a, b, T_obs):
    """Processo gerador do BG/NBD. Devolve x, t_x, T e a lista de tempos."""
    lam = RNG.gamma(r, 1.0 / alpha, n)
    p = RNG.beta(a, b, n)
    T = np.full(n, T_obs, float) if np.isscalar(T_obs) else np.asarray(T_obs, float)

    x = np.zeros(n)
    t_x = np.zeros(n)
    for i in range(n):
        t, vivo = 0.0, True
        while vivo:
            t += RNG.exponential(1.0 / lam[i])
            if t > T[i]:
                break
            x[i] += 1
            t_x[i] = t
            if RNG.random() < p[i]:      # morre DEPOIS da compra
                vivo = False
    return x, t_x, T


def test_recupera_parametros_bgnbd():
    r, alpha, a, b = 0.8, 4.0, 1.2, 2.5
    x, t_x, T = simular_bgnbd(4000, r, alpha, a, b, T_obs=24.0)
    m = BGNBD().fit(x, t_x, T)
    est = m.params_
    print("BG/NBD  verdadeiro:", dict(r=r, alpha=alpha, a=a, b=b))
    print("BG/NBD  estimado  :", {k: round(v, 3) for k, v in est.items()})

    # razoes r/alpha (taxa media de compra) e a/(a+b) (prob de churn) sao os
    # funcionais identificaveis com mais estabilidade
    assert abs(est["r"] / est["alpha"] - r / alpha) < 0.35 * (r / alpha)
    assert abs(est["a"] / (est["a"] + est["b"]) - a / (a + b)) < 0.10
    print("ok: parametros recuperados")


def test_formula_fechada_bate_com_simulacao():
    """E[X(t)] fechado (hyp2f1) vs media de clientes novos simulados."""
    r, alpha, a, b = 0.8, 4.0, 1.2, 2.5
    m = BGNBD()
    m.params_ = {"r": r, "alpha": alpha, "a": a, "b": b}
    for t in [3.0, 6.0, 12.0]:
        x, _, _ = simular_bgnbd(20000, r, alpha, a, b, T_obs=t)
        esperado = float(m.transacoes_esperadas(t))
        obtido = x.mean()
        erro = abs(esperado - obtido) / obtido
        print(f"E[X({t:>4.0f})]  formula={esperado:6.3f}  simulado={obtido:6.3f}"
              f"  erro={erro:.2%}")
        assert erro < 0.05
    print("ok: formula fechada confere com a simulacao")


def test_condicional_e_monotona():
    """Quem comprou mais e mais recentemente tem previsao maior."""
    m = BGNBD()
    m.params_ = {"r": 0.8, "alpha": 4.0, "a": 1.2, "b": 2.5}
    # os tres primeiros estao igualmente ativos (comprou ha pouco); muda so a
    # frequencia. o quarto comprou muito mas sumiu ha 19 meses.
    freq = np.array([0.0, 2.0, 10.0, 10.0])
    rec = np.array([0.0, 22.0, 22.0, 5.0])
    T = np.array([24.0, 24.0, 24.0, 24.0])
    prev = m.transacoes_condicionais(6.0, freq, rec, T)
    vivo = m.prob_vivo(freq, rec, T)
    print("previsao 6m:", prev.round(3), " p(vivo):", vivo.round(3))
    assert prev[2] > prev[1] > prev[0]          # mais frequente -> mais compras
    assert prev[2] > prev[3]                    # recente > sumido
    assert vivo[2] > vivo[3]
    assert np.all(prev >= 0)
    print("ok: condicional monotona e p(vivo) coerente")


def test_recupera_parametros_gamma_gamma():
    p, q, v = 6.0, 4.0, 15.0
    n = 5000
    nu = RNG.gamma(q, 1.0 / v, n)
    x = RNG.poisson(5, n) + 1.0
    m_x = np.array([RNG.gamma(p * xi, 1.0 / (nu[i] * xi))
                    for i, xi in enumerate(x)])
    gg = GammaGamma().fit(x, m_x)
    est = gg.params_
    print("GG verdadeiro:", dict(p=p, q=q, v=v))
    print("GG estimado  :", {k: round(val, 3) for k, val in est.items()})

    tm_verd = p * v / (q - 1)
    tm_est = gg.ticket_medio_populacional()
    print(f"ticket populacional verdadeiro={tm_verd:.2f} estimado={tm_est:.2f}")
    assert abs(tm_est - tm_verd) / tm_verd < 0.10

    # condicional fica entre o ticket individual e o populacional
    cond = gg.ticket_condicional(x, m_x)
    assert np.all(np.minimum(m_x, tm_est) - 1e-6 <= cond)
    assert np.all(cond <= np.maximum(m_x, tm_est) + 1e-6)
    print("ok: Gamma-Gamma recuperado e condicional dentro dos limites")


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            print(f"\n--- {nome} ---")
            fn()
    print("\nTODOS OS TESTES PASSARAM")
