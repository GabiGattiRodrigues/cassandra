"""Baixa a base Online Retail II (UCI) para data/.

Fonte oficial: https://archive.ics.uci.edu/dataset/502/online+retail+ii
Se o link da UCI estiver fora do ar, o script cai para um espelho no GitHub.
"""
import pathlib
import urllib.request

DESTINO = pathlib.Path(__file__).resolve().parents[1] / "data"
DESTINO.mkdir(exist_ok=True)
ARQ = DESTINO / "online_retail_II.xlsx"

FONTES = [
    "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip",
    "https://raw.githubusercontent.com/rposhala/"
    "Data_Analysis_of_Online_Retail_datasets/master/online_retail_II.xlsx",
]

if ARQ.exists():
    print(f"ja existe: {ARQ} ({ARQ.stat().st_size / 1e6:.0f} MB)")
    raise SystemExit

for url in FONTES:
    try:
        print("baixando", url)
        alvo = DESTINO / ("online_retail_II.zip" if url.endswith(".zip") else
                          "online_retail_II.xlsx")
        urllib.request.urlretrieve(url, alvo)
        if alvo.suffix == ".zip":
            import zipfile
            with zipfile.ZipFile(alvo) as z:
                z.extractall(DESTINO)
            alvo.unlink()
        print(f"ok -> {ARQ} ({ARQ.stat().st_size / 1e6:.0f} MB)")
        break
    except Exception as e:            # noqa: BLE001
        print("  falhou:", e)
else:
    raise SystemExit("nenhuma fonte respondeu; baixe manualmente da UCI")
