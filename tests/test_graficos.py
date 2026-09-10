"""Smoke test: monta todos os graficos e confere que nao ha figura vazia."""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "app"))
import pandas as pd, numpy as np
import graficos as G
from modelo.safras import (agregar_por_safra, segmentos_marcos,
                           mape_dos_paineis, mape_por_mes,
                           simular_safra, METRICAS)
from modelo.btyd import BGNBD, GammaGamma

D = pathlib.Path(__file__).resolve().parents[1] / "app" / "dados"
painel = pd.read_parquet(D / "painel_safras.parquet")
meta = json.loads((D / "modelo.json").read_text())
elast = pd.read_parquet(D / "elasticidade_cliente.parquet")
ULT = meta["cortes"][-1]

agg = agregar_por_safra(painel[painel["corte"] == ULT])
safras = sorted(agg["safra"].unique())
print(f"safras: {len(safras)} | linhas agg: {len(agg)}")

for nome, (ct, cr, fmt, acum) in METRICAS.items():
    if not acum:
        f = G.barras_camadas(agg, ct, fmt, nome)
        assert len([t for t in f.data if t.type == 'bar']) == 4, nome
        assert f.layout.barmode == 'overlay', nome
        print(f"  ok barras de nivel: {nome}")
        continue
    seg = segmentos_marcos(agg, ct, cr)
    f = G.barras_empilhadas(seg, fmt, nome)
    assert len(f.data) > 0, nome
    # uma barra por safra: a pilha tem que somar o acumulado em M12
    assert f.layout.barmode == "stack"
    barras = [tr for tr in f.data if tr.type == "bar"]
    ys = np.array([list(tr.y) for tr in barras])
    ordem = list(barras[0].x)
    for si, s_ in enumerate(ordem):
        pilha = ys[:, si].sum()
        esperado = agg[(agg.safra == s_) & (agg.m == 12)][ct].iloc[0]
        assert abs(pilha - esperado) < max(1e-4, abs(esperado) * 1e-6), \
            f"{nome} {s_}: pilha={pilha:.4f} M12={esperado:.4f}"
    print(f"     pilha = acumulado M12 em {len(ordem)} barras")
    # o acumulado tem que bater com a soma dos segmentos
    for s in safras[:4]:
        d = seg[seg.safra == s].sort_values("ordem")
        assert abs(d["delta"].sum() - d["valor_acum"].iloc[-1]) < 1e-6, (nome, s)
        for _, l in d.iterrows():
            assert abs(l["delta_realizado"] + l["delta_previsto"] - l["delta"]) < 1e-4 \
                or l["delta"] < 0, (nome, s, l["segmento"])
    print(f"  ok barras: {nome} ({len(f.data)} traces)")

f = G.linhas_por_safra(agg, "rec_cliente", safras[-6:]); assert len(f.data) > 0
print("ok linhas:", len(f.data), "traces")
f = G.barras_comparando_safras(agg, 12, "rec_cliente"); assert len(f.data) > 0
print("ok barras comparativas:", len(f.data), "traces")
# em M0 a barra tem que ser so o realizado
f0 = G.barras_comparando_safras(agg, 0, "rec_cliente", "R$ {:,.0f}", "rec_cliente_real")
assert all("previsto" not in (t.name or "").lower() for t in f0.data), "M0 nao pode ter previsto"
y0 = sum(sum(t.y) for t in f0.data if t.type == "bar")
esperado0 = agg[agg.m == 0].rec_cliente_real.sum()
assert abs(y0 - esperado0) < 1e-3, f"M0: {y0} vs {esperado0}"
print("ok M0 so realizado")

# MAPE por safra x mes de vida
pn = painel.copy(); pn["corte"] = pn["corte"].astype(str)
mpm, viesm, nc, mel, pio, ant = mape_por_mes(pn, ULT, "rec_cliente")
ncel = int(mpm.notna().sum().sum())
assert ncel > 100, f"pontuou so {ncel} celulas"
assert list(mpm.columns) == sorted(mpm.columns), "colunas tem que ser M0..M12"
# coerencia: o mape medio fica entre o melhor e o pior corte da celula
ok = mpm.notna().to_numpy()          # comparar so onde ha celula (NaN <= NaN e False)
A, B, C, N = mpm.to_numpy(), mel.to_numpy(), pio.to_numpy(), nc.to_numpy()
assert (B[ok] <= A[ok] + 1e-9).all(), "mape medio abaixo do melhor corte"
assert (A[ok] <= C[ok] + 1e-9).all(), "mape medio acima do pior corte"
assert (N[ok] >= 1).all(), "celula pontuada sem previsao"
# celula com uma previsao so: melhor = pior = mape
um = ok & (N == 1)
assert np.allclose(B[um], C[um]) and np.allclose(A[um], B[um]), "n=1 inconsistente"
print(f"ok MAPE por mes: {ncel} celulas, {int(np.nansum(nc.values))} previsoes | "
      f"medio {np.nanmean(mpm.values):.1f}%")
f = G.matriz_mape(mpm, viesm, extra=nc, rot_extra="previsoes",
                  extra2=mel, rot_extra2="melhor", extra3=pio, rot_extra3="pior")
assert f is not None

mp, vi, p, r = mape_dos_paineis(painel, meta["cortes"][1], ULT, "rec_cliente")
f = G.matriz_mape(mp, vi); assert f is not None
print("ok matriz mape:", int(np.isfinite(mp.to_numpy()).sum()), "celulas |",
      f"MAPE medio {np.nanmean(mp.to_numpy()):.1f}%")

m = meta["por_corte"][ULT]
bg = BGNBD(); bg.params_ = m["bgnbd"]; gg = GammaGamma(); gg.params_ = m["gamma_gamma"]
sim = simular_safra(bg, gg, 500, m["ticket_m0_medio"], m["ticket_m0_medio"],
                    m["ticket_recompra_medio"], m["elasticidade_ticket"])
assert sim["rec_cliente"].is_monotonic_increasing, "acumulado tem que subir"
assert sim["freq"].is_monotonic_increasing
fechadas = agg[(agg.frac_observada > .999) & (agg.m == 12)].safra
f = G.curva_simulada(sim, agg, "rec_cliente", list(fechadas)); assert len(f.data) > 0
print("ok simulador + curva:", len(f.data), "traces")
f = G.dispersao_elasticidade(elast, m["elasticidade_ticket"], m["elasticidade_r2"])
print("ok dispersao:", len(f.data), "traces")

# acumulado nunca pode cair
for s in safras:
    d = agg[agg.safra == s].sort_values("m")
    assert d["rec_acum"].is_monotonic_increasing, f"acumulado caiu na safra {s}"
    assert d["trans_acum"].is_monotonic_increasing, f"transacoes cairam em {s}"
print("ok: acumulado monotono em todas as safras")
print("\nTODOS OS SMOKE TESTS PASSARAM")
