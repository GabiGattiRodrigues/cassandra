"""Carrega Online Retail II (2 abas), limpa e salva parquet de transacoes."""
import pandas as pd, numpy as np, pathlib

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "online_retail_II.xlsx"
OUT = pathlib.Path(__file__).resolve().parents[1] / "data"

frames = []
for sheet in ["Year 2009-2010", "Year 2010-2011"]:
    df = pd.read_excel(RAW, sheet_name=sheet, engine="openpyxl")
    df["_sheet"] = sheet
    frames.append(df)
    print(sheet, df.shape)

df = pd.concat(frames, ignore_index=True)
df.columns = [c.strip().replace(" ", "_") for c in df.columns]
print("colunas:", list(df.columns))
print(df.head(3))
print(df.dtypes)
df.to_pickle(OUT / "raw_concat.pkl")
print("total bruto:", df.shape)
