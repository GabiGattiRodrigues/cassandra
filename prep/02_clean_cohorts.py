"""Limpeza + painel de safras (cohorts) por aniversario do cliente."""
import pandas as pd, numpy as np, pathlib

BASE = pathlib.Path(__file__).resolve().parents[1]
df = pd.read_pickle(BASE / "data" / "raw_concat.pkl")
n0 = len(df)

log = []
def step(msg, d):
    log.append(f"{msg:<45} {len(d):>9,}  ({len(d)/n0:6.1%})")
    return d

df["Invoice"] = df["Invoice"].astype(str).str.strip()
df["StockCode"] = df["StockCode"].astype(str).str.strip().str.upper()

df = step("bruto", df)
df = step("com Customer_ID", df[df["Customer_ID"].notna()])
df = step("sem cancelamento (invoice C*)", df[~df["Invoice"].str.startswith("C")])
df = step("quantidade > 0", df[df["Quantity"] > 0])
df = step("preco > 0", df[df["Price"] > 0])

# codigos que nao sao produto (frete, ajuste, taxa bancaria, amostra, etc.)
NAO_PRODUTO = {"POST", "D", "DOT", "M", "S", "AMAZONFEE", "BANK CHARGES", "B",
               "CRUK", "PADS", "C2", "GIFT", "TEST001", "TEST002", "ADJUST",
               "ADJUST2", "SP1002", "DCGS0076", "DCGS0003"}
df = step("codigo de produto valido", df[~df["StockCode"].isin(NAO_PRODUTO)])
df = step("stockcode alfanumerico de produto",
          df[df["StockCode"].str.match(r"^\d{5}[A-Z]*$")])

df["receita"] = df["Quantity"] * df["Price"]
df["Customer_ID"] = df["Customer_ID"].astype(int)

# ---- nivel transacao: 1 compra = 1 invoice ----
tx = (df.groupby(["Customer_ID", "Invoice"], as_index=False)
        .agg(data=("InvoiceDate", "min"),
             receita=("receita", "sum"),
             itens=("Quantity", "sum"),
             skus=("StockCode", "nunique"),
             pais=("Country", "first")))
tx["data"] = tx["data"].dt.normalize()
tx = tx[tx["receita"] > 0]
log.append(f"{'transacoes (invoices)':<45} {len(tx):>9,}")
log.append(f"{'clientes':<45} {tx.Customer_ID.nunique():>9,}")
log.append(f"{'periodo':<45} {tx.data.min().date()} a {tx.data.max().date()}")

# ---- corte de observacao: descarta dezembro/2011 parcial ----
FIM = pd.Timestamp("2011-11-30")
tx = tx[tx["data"] <= FIM]

# ---- safra = mes da primeira compra ----
prim = (tx.sort_values("data").groupby("Customer_ID")
          .agg(data_1a=("data", "first"),
               receita_1a=("receita", "first"),
               pais=("pais", "first")))
prim["safra"] = prim["data_1a"].dt.to_period("M").astype(str)

# tipo de cliente = faixa de ticket da 1a compra (tercis calculados no total)
q = prim["receita_1a"].quantile([1/3, 2/3]).values
prim["tipo_cliente"] = np.where(prim["receita_1a"] <= q[0], "Entrada baixa",
                        np.where(prim["receita_1a"] <= q[1], "Entrada media", "Entrada alta"))
prim["regiao"] = np.where(prim["pais"] == "United Kingdom", "Reino Unido", "Fora do Reino Unido")

tx = tx.merge(prim[["data_1a", "safra", "tipo_cliente", "regiao"]],
              left_on="Customer_ID", right_index=True, how="left")
tx["dias"] = (tx["data"] - tx["data_1a"]).dt.days

print("\n".join(log))
print("\ncortes de ticket 1a compra:", q.round(2))
print("\nsafras:")
print(prim.groupby("safra").size().to_string())
print("\ntipo de cliente:"); print(prim.tipo_cliente.value_counts().to_string())
print("\nregiao:"); print(prim.regiao.value_counts().to_string())

# taxa de recompra: essencial pro BG/NBD fazer sentido
nc = tx.groupby("Customer_ID").size()
print(f"\n%% clientes com >=2 compras: {(nc>=2).mean():.1%}")
print(f"media de compras por cliente: {nc.mean():.2f}  mediana: {nc.median():.0f}")
print(f"ticket medio geral: {tx.receita.mean():.2f}  mediana: {tx.receita.median():.2f}")

tx.to_parquet(BASE / "data" / "transacoes.parquet", index=False)
prim.reset_index().to_parquet(BASE / "data" / "clientes.parquet", index=False)
pathlib.Path(BASE / "data" / "log_limpeza.txt").write_text(
    "\n".join(log), encoding="utf-8")
print("\nok -> transacoes.parquet / clientes.parquet")
