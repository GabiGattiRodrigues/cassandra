"""
Conferencia independente: recalcula o realizado direto das transacoes limpas,
por um caminho de codigo diferente do pipeline, e compara com o painel que o
app le. Se o numero do dashboard nao bater com a base, quebra aqui.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "app"))
import pandas as pd, numpy as np
from dateutil.relativedelta import relativedelta
from modelo.safras import agregar_por_safra

B = pathlib.Path(__file__).resolve().parents[1]
tx = pd.read_parquet(B / "data" / "transacoes.parquet")
cli = pd.read_parquet(B / "data" / "clientes.parquet")
painel = pd.read_parquet(B / "app" / "dados" / "painel_safras.parquet")

# mesma exclusao do prep: safra censurada a esquerda
cli = cli[cli.safra != "2009-12"]
tx = tx[tx.Customer_ID.isin(cli.Customer_ID)]

agg = agregar_por_safra(painel[painel.corte == "2011-11-30"])
agg["safra"] = agg.safra.astype(str)

prim = cli.set_index("Customer_ID")["data_1a"]
falhas = 0
for k in [0, 3, 6, 12]:
    # caminho independente: laco explicito com relativedelta, sem numpy
    lim = {c: d + relativedelta(months=k + 1) - pd.Timedelta(days=1)
           for c, d in prim.items()}
    t = tx.copy()
    t["limite"] = t.Customer_ID.map(lim)
    dentro = t[t.data <= t.limite]
    ref = (dentro.groupby(dentro.Customer_ID.map(cli.set_index("Customer_ID").safra))
                 .agg(receita=("receita", "sum"), n=("receita", "size")))
    n_cli = cli.groupby("safra").size()
    ref["rec_cliente"] = ref.receita / n_cli
    ref["freq"] = ref.n / n_cli

    for safra in ref.index:
        linha = agg[(agg.safra == safra) & (agg.m == k)]
        if linha.empty or linha.frac_observada.iloc[0] <= 0.999:
            continue          # so confere o que esta 100% realizado
        for col in ["rec_cliente", "freq"]:
            a, b = float(linha[col].iloc[0]), float(ref.loc[safra, col])
            if abs(a - b) > max(0.01, abs(b) * 1e-4):
                print(f"  DIVERGE M{k} {safra} {col}: painel={a:.4f} base={b:.4f}")
                falhas += 1
    print(f"M{k}: conferido contra a base bruta")

assert falhas == 0, f"{falhas} divergencias entre o painel e a base"
print("\nok: todo realizado do painel bate com o recalculo direto das transacoes")

# a receita total do painel nao pode passar da receita que existe na base
total_base = tx.receita.sum()
total_real = agg[agg.m == 12].rec_real.sum()
print(f"receita realizada M12 no painel: {total_real:,.0f} | "
      f"receita total na base: {total_base:,.0f}")
assert total_real <= total_base * 1.0001, "painel inventou receita"
print("ok: painel nao inventa receita")
