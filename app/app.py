"""
Cassandra - previsao de ticket medio, frequencia e receita por safra.

BG/NBD + Gamma-Gamma sobre a base publica Online Retail II, com a leitura de
cohort M0 / M3 / M6 / M12 separando o que ja aconteceu do que o modelo preve.
"""
import json
import pathlib

import numpy as np
import pandas as pd
import streamlit as st

import graficos as G
import i18n
import tema as T
from i18n import L
from modelo.btyd import BGNBD, GammaGamma
from modelo.safras import (METRICAS, agregar_por_safra, mape_por_mes,
                           segmentos_marcos, simular_safra)

AQUI = pathlib.Path(__file__).resolve().parent
DADOS = AQUI / "dados"

i18n.iniciar()
st.set_page_config(page_title=L("Cassandra · previsão de safras",
                                "Cassandra · vintage forecasting"),
                   page_icon=str(AQUI / "assets" / "favicon.png")
                   if (AQUI / "assets" / "favicon.png").exists() else "🔮",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  .stApp { background:#f9f9f7; }
  section[data-testid="stSidebar"] { background:#ffffff;
      border-right:1px solid #e1e0d9; }
  h1,h2,h3 { color:#0b0b0b; letter-spacing:-.01em; }
  .cart { background:#fcfcfb; border:1px solid #e1e0d9; border-radius:12px;
          padding:14px 16px; height:100%; }
  .cart .rot { font-size:12px; color:#898781; text-transform:uppercase;
               letter-spacing:.04em; }
  .cart .val { font-size:26px; font-weight:650; color:#0b0b0b;
               line-height:1.25; margin-top:2px; }
  .cart .sub { font-size:12px; color:#52514e; margin-top:2px; }
  .tag { display:inline-block; font-size:11px; padding:2px 8px;
         border-radius:99px; border:1px solid #e1e0d9; color:#52514e;
         background:#fff; margin-right:6px; }
  .leg { display:flex; gap:14px; flex-wrap:wrap; align-items:center;
         font-size:12px; color:#52514e; margin:2px 0 10px; }
  .leg i { width:13px; height:13px; border-radius:3px; display:inline-block;
           margin-right:6px; vertical-align:-2px; }
  .nota { font-size:12.5px; color:#52514e; background:#fcfcfb;
          border-left:3px solid #2a78d6; padding:9px 13px; border-radius:0 8px 8px 0; }
  [data-testid="stMetricValue"] { font-size:24px; }
  .stTabs [data-baseweb="tab"] { font-size:14px; }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def carregar():
    painel = pd.read_parquet(DADOS / "painel_safras.parquet")
    meta = json.loads((DADOS / "modelo.json").read_text(encoding="utf-8"))
    elast_cli = pd.read_parquet(DADOS / "elasticidade_cliente.parquet")
    backtest = pd.read_parquet(DADOS / "backtest_safra.parquet")
    return painel, meta, elast_cli, backtest


@st.cache_data(show_spinner=False)
def agregado(corte: str, tipos: tuple, regioes: tuple):
    painel, _, _, _ = carregar()
    filtro = {"tipo_cliente": list(tipos), "regiao": list(regioes)}
    g = agregar_por_safra(painel[painel["corte"] == corte], filtro)
    g["safra"] = g["safra"].astype(str)   # sai de Categorical: precisa comparar
    return g


@st.cache_data(show_spinner="Rodando o backtest…")
def mape_mes(verdade: str, metrica: str, tipos: tuple, regioes: tuple):
    painel, _, _, _ = carregar()
    painel = painel.copy()
    painel["corte"] = painel["corte"].astype(str)
    filtro = {"tipo_cliente": list(tipos), "regiao": list(regioes)}
    return mape_por_mes(painel, verdade, metrica, filtro)


MES_PT = i18n.MESES_PT

# Os valores do dado são gravados em português; a tradução é só na tela.
VALORES_EN = {"Entrada baixa": "Low entry ticket",
              "Entrada media": "Mid entry ticket",
              "Entrada alta": "High entry ticket",
              "Reino Unido": "United Kingdom",
              "Fora do Reino Unido": "Outside the UK",
              "Simulada": "Simulated"}
METRICAS_EN = {"Receita por cliente": "Revenue per customer",
               "Frequência de compra": "Purchase frequency",
               "Receita total": "Total revenue",
               "Ticket médio": "Average ticket"}


def V(v):
    return VALORES_EN.get(str(v), str(v)) if i18n.en() else str(v)


def mes_pt(d):
    """strftime usa o locale C e devolve 'Feb'; aqui o rótulo sai na língua
    ativa: 'fev/11' em português, 'Feb 11' em inglês."""
    d = pd.Timestamp(d)
    if i18n.en():
        return f"{i18n.MESES_EN[d.month - 1]} {d.year % 100:02d}"
    return f"{MES_PT[d.month - 1]}/{d.year % 100:02d}"


def data_longa(d):
    d = pd.Timestamp(d)
    if i18n.en():
        return f"{i18n.MESES_EN[d.month - 1]} {d.day}, {d.year}"
    return d.strftime("%d/%m/%Y")


def ler_md(nome: str) -> str:
    """O texto longo da aba, na língua ativa (arquivo irmão com _en)."""
    arq = AQUI / (nome.replace(".md", "_en.md") if i18n.en() else nome)
    if not arq.exists():
        arq = AQUI / nome
    return arq.read_text(encoding="utf-8")


def plot(fig):
    """theme=None: o Streamlit reescreve barmode e legenda quando aplica o tema
    dele por cima. Os gráficos aqui já vêm com paleta e layout próprios."""
    st.plotly_chart(fig, use_container_width=True, theme=None)


painel, meta, elast_cli, backtest = carregar()
CORTES = meta["cortes"]
ULTIMO = CORTES[-1]

# --------------------------------------------------------------------------- #
with st.sidebar:
    i18n.seletor()
    st.markdown("### 🔮 Cassandra")
    st.caption(L("Previsão de ticket, frequência e receita por safra",
                 "Ticket, frequency and revenue forecast by vintage"))
    st.divider()

    st.markdown(L("**Data de corte**", "**Cutoff date**"))
    st.caption(L("Tudo até aqui é realizado. Daqui pra frente, é o modelo "
                 "falando.",
                 "Everything up to here is actual. From here on, it's the "
                 "model talking."))
    corte = st.select_slider(" ", options=CORTES, value=ULTIMO,
                             format_func=mes_pt,
                             label_visibility="collapsed")

    # A chave da métrica é o nome em português; o que muda com a língua é
    # só o texto mostrado.
    metrica_chave = st.selectbox(
        L("Métrica", "Metric"), list(METRICAS.keys()),
        format_func=lambda k: METRICAS_EN.get(k, k) if i18n.en() else k)
    metrica_nome = METRICAS_EN.get(metrica_chave, metrica_chave) \
        if i18n.en() else metrica_chave
    col_total, col_real, formato, acumulavel = METRICAS[metrica_chave]

    st.divider()
    st.markdown(L("**Recortes**", "**Slices**"))
    tipos_all = sorted(painel["tipo_cliente"].dropna().unique().tolist())
    regioes_all = sorted(painel["regiao"].dropna().unique().tolist())
    tipos = st.multiselect(L("Tipo de cliente (faixa de ticket na 1ª compra)",
                             "Customer type (1st-purchase ticket band)"),
                           tipos_all, default=tipos_all, format_func=V)
    regioes = st.multiselect(L("Região", "Region"), regioes_all,
                             default=regioes_all, format_func=V)
    if not tipos:
        tipos = tipos_all
    if not regioes:
        regioes = regioes_all

    safras_all = sorted(painel["safra"].dropna().unique().tolist())
    ini, fim = st.select_slider(
        L("Safras na visão", "Vintages in view"), options=safras_all,
        value=(safras_all[0], safras_all[-1]),
        help=L("Menos safras = gráfico mais legível. A conta não muda.",
               "Fewer vintages = a more readable chart. The math doesn't "
               "change."))

    st.divider()
    m_info = meta["por_corte"][corte]

    # o simulador vive na aba 4, mas a aba 1 roda antes dela no script. Guardar
    # os parametros em session_state deixa os dois lados lendo o mesmo valor:
    # o widget da aba 4 escreve na chave, e no rerun seguinte a aba 1 le dali.
    st.session_state.setdefault("sim_tm0", float(round(m_info["ticket_m0_medio"])))
    st.session_state.setdefault("sim_ncli", 500)
    st.session_state.setdefault("sim_elast",
                                float(round(m_info["elasticidade_ticket"], 2)))
    mostrar_sim = st.checkbox(
        L("Incluir a safra simulada nos gráficos",
          "Include the simulated vintage in the charts"), value=False,
        help=L("A safra que você monta na aba 'Simular safra nova' entra como "
               "mais uma barra, toda hachurada — ela é 100% previsão.",
               "The vintage you build in the 'Simulate a new vintage' tab "
               "shows up as one more bar, fully hatched — it's 100% "
               "forecast."))

    st.markdown(L("**Modelo ajustado neste corte**",
                  "**Model fitted at this cutoff**"))
    st.markdown(
        f"<span class='tag'>r {m_info['bgnbd']['r']:.3f}</span>"
        f"<span class='tag'>α {m_info['bgnbd']['alpha']:.3f}</span>"
        f"<span class='tag'>a {m_info['bgnbd']['a']:.3f}</span>"
        f"<span class='tag'>b {m_info['bgnbd']['b']:.3f}</span>",
        unsafe_allow_html=True)
    st.caption(L(f"{i18n.num(m_info['n_clientes'])} clientes · "
                 f"{m_info['pct_repetidores']:.0%} com recompra · "
                 f"corr(freq,ticket) = "
                 f"{i18n.num(m_info['corr_freq_ticket'], 3)}",
                 f"{i18n.num(m_info['n_clientes'])} customers · "
                 f"{m_info['pct_repetidores']:.0%} with repeat purchase · "
                 f"corr(freq,ticket) = {m_info['corr_freq_ticket']:+.3f}"))

agg_todas = agregado(corte, tuple(tipos), tuple(regioes))
agg = agg_todas[(agg_todas["safra"] >= ini) & (agg_todas["safra"] <= fim)].copy()

NOME_SIM = L("Simulada", "Simulated")
bg_sim = BGNBD(); bg_sim.params_ = m_info["bgnbd"]
gg_sim = GammaGamma(); gg_sim.params_ = m_info["gamma_gamma"]
sim_curva = simular_safra(
    bg_sim, gg_sim, int(st.session_state["sim_ncli"]),
    float(st.session_state["sim_tm0"]), float(m_info["ticket_m0_medio"]),
    float(m_info["ticket_recompra_medio"]), float(st.session_state["sim_elast"]))

if mostrar_sim:
    # a safra simulada e 100% previsao: tudo que e "_real" fica zerado e a
    # fracao observada e 0, entao ela sai hachurada em todos os graficos
    n = int(st.session_state["sim_ncli"])
    linha_sim = pd.DataFrame({
        "safra": NOME_SIM, "m": sim_curva["m"], "clientes": n,
        "trans_real": 0.0, "rec_real": 0.0,
        "trans_prev": sim_curva["freq"] * n, "rec_prev": sim_curva["rec_acum"],
        "n_obs": 0,
        "trans_acum": sim_curva["freq"] * n, "rec_acum": sim_curva["rec_acum"],
        "freq": sim_curva["freq"], "rec_cliente": sim_curva["rec_cliente"],
        "ticket": sim_curva["ticket"], "frac_observada": 0.0,
        "freq_real": 0.0, "rec_cliente_real": 0.0, "ticket_real": 0.0,
    })
    agg = pd.concat([agg, linha_sim], ignore_index=True)

safras = sorted(agg["safra"].unique().tolist())

# --------------------------------------------------------------------------- #
c1, c2 = st.columns([0.62, 0.38])
with c1:
    st.markdown("## Cassandra")
    st.markdown(L(
        "**Quanto uma safra de clientes vai valer em M3, M6 e M12** — "
        "modelada com BG/NBD + Gamma-Gamma, com o realizado e o previsto "
        "no mesmo gráfico.",
        "**How much a vintage of customers will be worth at M3, M6 and "
        "M12** — modeled with BG/NBD + Gamma-Gamma, with actual and forecast "
        "on the same chart."))
with c2:
    logo = AQUI / "assets" / "cassandra.svg"
    if logo.exists():
        st.image(str(logo), width=250)

# cartoes do periodo (a safra simulada fica de fora: eles descrevem a base real)
agg_reais = agg[agg["safra"] != NOME_SIM]
alvo = agg_reais[agg_reais["m"] == 12]
obs = alvo[alvo["frac_observada"] > 0.999]
prev = alvo[alvo["frac_observada"] <= 0.999]
k1, k2, k3, k4 = st.columns(4)


def cart(col, rot, val, sub):
    col.markdown(f"<div class='cart'><div class='rot'>{rot}</div>"
                 f"<div class='val'>{val}</div><div class='sub'>{sub}</div></div>",
                 unsafe_allow_html=True)


cart(k1, L("Safras na visão", "Vintages in view"),
     f"{agg_reais['safra'].nunique()}",
     L(f"{i18n.num(alvo['clientes'].sum())} clientes",
       f"{i18n.num(alvo['clientes'].sum())} customers"))
cart(k2, L("Safras já fechadas em M12", "Vintages already closed at M12"),
     f"{len(obs)}",
     L("realizado completo, sem modelo", "fully actual, no model"))
cart(k3, L("Safras em previsão", "Vintages in forecast"), f"{len(prev)}",
     L("M12 ainda não aconteceu", "M12 hasn't happened yet"))
if len(alvo):
    v = alvo["rec_acum"].sum() / max(alvo["clientes"].sum(), 1)
    vp = (prev["rec_acum"].sum() / max(prev["clientes"].sum(), 1)) if len(prev) else 0
    cart(k4, L("Receita/cliente em M12", "Revenue/customer at M12"),
         f"R$ {i18n.num(v)}",
         L(f"safras em previsão: R$ {i18n.num(vp)}",
           f"vintages in forecast: R$ {i18n.num(vp)}") if vp else
         L("todas realizadas", "all actual"))

st.markdown(
    L(f"<div class='nota'>Corte em <b>{data_longa(corte)}</b>. "
      "Barra cheia e linha sólida = o que já aconteceu. "
      "Barra hachurada e linha pontilhada = previsão do modelo.</div>",
      f"<div class='nota'>Cutoff on <b>{data_longa(corte)}</b>. "
      "Solid bar and solid line = what already happened. "
      "Hatched bar and dotted line = the model's forecast.</div>"),
    unsafe_allow_html=True)
st.write("")

# --------------------------------------------------------------------------- #
abas = st.tabs(L(["Safras", "Comparar um M", "Qualidade da previsão",
                  "Simular safra nova", "Como o modelo foi feito", "Glossário",
                  "O case"],
                 ["Vintages", "Compare one M", "Forecast quality",
                  "Simulate a new vintage", "How the model was built",
                  "Glossary", "The case"]))

# ---------------------------------------------------------------- SAFRAS ----
with abas[0]:
    st.markdown(
        "<div class='leg'>"
        + "".join(f"<span><i style='background:{c}'></i>{n}</span>"
                  for n, c in T.MARCOS_COR.items())
        + "<span style='color:#898781'>│ "
        + L("hachura = previsto", "hatching = forecast") + "</span></div>",
        unsafe_allow_html=True)
    if acumulavel:
        seg = segmentos_marcos(agg, col_total, col_real)
        st.plotly_chart(
            G.barras_empilhadas(
                seg, formato,
                L(f"{metrica_nome} acumulada — M0, M3, M6 e M12 por safra",
                  f"Cumulative {metrica_nome.lower()} — M0, M3, M6 and M12 "
                  f"by vintage")),
            use_container_width=True, theme=None)
        st.caption(L(
            "Cada barra é uma safra. De baixo para cima: o M0, o que ela "
            "somou até M3, até M6 e até M12 — a altura total é o "
            "acumulado em M12. A cor de cada faixa é a mesma em todas "
            "as safras, então dá para comparar faixa por faixa na "
            "horizontal.",
            "Each bar is a vintage. From bottom to top: M0, what it added up "
            "to M3, to M6 and to M12 — the total height is the cumulative "
            "value at M12. Each band has the same color in every vintage, so "
            "you can compare band by band across the chart."))
    else:
        st.plotly_chart(
            G.barras_camadas(
                agg, col_total, formato,
                L(f"{metrica_nome} em cada marco, por safra",
                  f"{metrica_nome} at each milestone, by vintage")),
            use_container_width=True, theme=None)
        st.caption(L(
            "Ticket médio não é acumulável — o de M12 não é o de M0 mais um "
            "pedaço, é uma média que se move e pode até cair. Então cada faixa "
            "de cor vai de zero até o **nível** daquele marco: o topo de cada "
            "cor é o ticket ali, e a barra inteira é a curva do ticket vista "
            "de lado.",
            "Average ticket isn't cumulative — M12's isn't M0's plus a piece, "
            "it's an average that moves and can even fall. So each color band "
            "goes from zero to the **level** at that milestone: the top of "
            "each color is the ticket there, and the whole bar is the ticket "
            "curve seen from the side."))

    st.divider()
    padrao = safras[-6:] if len(safras) > 6 else safras
    sel = st.multiselect(L("Safras no gráfico de linhas (até 8)",
                           "Vintages in the line chart (up to 8)"), safras,
                         default=padrao, max_selections=8)
    if sel:
        st.plotly_chart(
            G.linhas_por_safra(agg, col_total, sorted(sel), formato,
                               L(f"{metrica_nome} acumulada ao longo da vida",
                                 f"Cumulative {metrica_nome.lower()} over "
                                 f"the customer lifetime")),
            use_container_width=True, theme=None)
    with st.expander(L("Ver os números", "See the numbers")):
        tab = agg.pivot(index="safra", columns="m", values=col_total)
        obs = agg.pivot(index="safra", columns="m", values="frac_observada")
        tab.columns = [f"M{c}" for c in tab.columns]
        obs.columns = tab.columns
        realizado = obs > 0.999

        def pintar(_):
            return pd.DataFrame(
                np.where(realizado,
                         "",
                         "background-color:#eaf2fd;color:#0d366b;"
                         "font-style:italic"),
                index=tab.index, columns=tab.columns)

        st.caption(L("Fundo branco = **realizado**, já aconteceu na base. "
                     "Fundo azul em itálico = **previsto** pelo modelo.",
                     "White background = **actual**, already happened in the "
                     "base. Blue italic background = **forecast** by the "
                     "model."))
        st.dataframe(tab.style.apply(pintar, axis=None).format(
            lambda v: i18n.num(v, 2)), use_container_width=True)

# ------------------------------------------------------------ COMPARAR M ----
with abas[1]:
    m_sel = st.select_slider(L("Mês de vida", "Month of life"),
                             options=list(range(13)), value=12,
                             format_func=lambda k: f"M{k}")
    st.plotly_chart(
        G.barras_comparando_safras(agg, m_sel, col_total, formato, col_real),
        use_container_width=True, theme=None)
    if m_sel == 0:
        st.caption(L("Em M0 a barra é só o realizado: o primeiro mês de vida "
                     "de qualquer safra que já existe já aconteceu, então não "
                     "há o que prever ali.",
                     "At M0 the bar is actual only: the first month of life "
                     "of any existing vintage has already happened, so "
                     "there's nothing to forecast there."))
    col_uso = col_real if m_sel == 0 else col_total
    d = agg[agg["m"] == m_sel].sort_values(col_uso, ascending=False)
    if len(d):
        c1, c2, c3 = st.columns(3)
        cart(c1, L(f"Melhor safra em M{m_sel}", f"Best vintage at M{m_sel}"),
             V(d.iloc[0]["safra"]), i18n.fmt(formato, d.iloc[0][col_uso]))
        cart(c2, L(f"Pior safra em M{m_sel}", f"Worst vintage at M{m_sel}"),
             V(d.iloc[-1]["safra"]), i18n.fmt(formato, d.iloc[-1][col_uso]))
        espalh = d.iloc[0][col_uso] / max(d.iloc[-1][col_uso], 1e-9)
        cart(c3, L("Distância entre elas", "Gap between them"),
             f"{i18n.num(espalh, 1)}×",
             L("quanto a melhor rende sobre a pior",
               "how much the best yields over the worst"))

# -------------------------------------------------------------- QUALIDADE ----
# Um passo a frente, sempre: com M0..M_{k-1} fechados da para prever o M_k, e so.
# Cada celula (safra, M_k) e uma previsao de um mes, feita com tudo que veio
# antes dela - a mesma leitura que se faz acompanhando a curva de um cohort.
# No backtest isso e a linha com origem = k-1.
with abas[2]:
    st.markdown(L("#### Quanto o modelo erra", "#### How much the model misses"))
    st.caption(L(
        "Cada mês é previsto com o que veio antes dele: com M0, M1 e M2 "
        "fechados prevê-se o M3; quando o M3 fecha, prevê-se o M4. Uma previsão "
        "de um mês por vez, que é como a curva de um cohort é acompanhada. "
        "Para cada safra o modelo é reajustado **sem nenhum cliente dela** "
        "(validação cruzada por safra). Cada safra entra até onde ela já "
        "fechou: para pontuar o M3 basta ter o M3 fechado, não os 13 meses. "
        "Por isso a matriz tem mais safras nos meses baixos e vai afinando.",
        "Each month is forecast with what came before it: with M0, M1 and M2 "
        "closed, M3 is forecast; when M3 closes, M4 is forecast. One month at "
        "a time, which is how a cohort curve is tracked. For each vintage the "
        "model is refitted **without any of its customers** (cross-validation "
        "by vintage). Each vintage counts as far as it has closed: to score M3 "
        "it only needs M3 closed, not all 13 months. That's why the matrix has "
        "more vintages in the early months and thins out."))

    ate = st.radio(L("Até onde mostrar", "Show up to"), [3, 6, 12], index=2,
                   horizontal=True,
                   format_func=lambda k: L(f"até o M{k}", f"up to M{k}"))

    bt = backtest[(backtest["origem"] == backtest["m"] - 1)
                  & (backtest["m"] >= 1) & (backtest["m"] <= ate)
                  & (backtest["metrica"] == col_total)
                  & (backtest["safra"].isin(safras))].copy()
    n_por_mes = bt.groupby("m")["safra"].nunique().to_dict()

    if bt.empty:
        st.warning(L("Nenhuma safra fechada neste recorte.",
                     "No closed vintage in this slice."))
    else:
        erro = bt.pivot(index="safra", columns="m", values="erro_pct")
        st.markdown(
            "<div class='leg'>"
            + "".join(f"<span><i style='background:{c}'></i>"
                      f"{T.FAIXAS_MAPE_EN[i] if i18n.en() else rot}</span>"
                      for i, (_, _, c, rot) in enumerate(T.FAIXAS_MAPE))
            + "</div>", unsafe_allow_html=True)

        st.plotly_chart(
            G.matriz_mape(
                erro.abs(), erro, margens=True,
                titulo=L("Erro de cada mês, previsto com o mês anterior fechado",
                         "Error for each month, forecast with the previous "
                         "month closed"),
                extra=bt.pivot(index="safra", columns="m", values="previsto"),
                rot_extra=L("previsto", "forecast"),
                extra2=bt.pivot(index="safra", columns="m", values="realizado"),
                rot_extra2=L("realizado", "actual"),
                sub_col={k: L(f"{v} safras", f"{v} vintages")
                         for k, v in n_por_mes.items()}),
            use_container_width=True, theme=None)
        st.caption(L(
            "Abaixo de cada M está quantas safras já fecharam aquele mês — a "
            "matriz vai afinando para a direita porque safra recente ainda não "
            "chegou lá. A última coluna é o erro médio de cada safra; a última "
            "linha é o erro médio de cada mês. O M0 não aparece porque não "
            "existe mês fechado antes dele para servir de base.",
            "Below each M is how many vintages have already closed that month "
            "— the matrix thins out to the right because recent vintages "
            "haven't got there yet. The last column is each vintage's average "
            "error; the last row is each month's average error. M0 doesn't "
            "show up because there's no closed month before it to use as a "
            "base."))

        z = erro.abs().to_numpy(float)
        k1, k2, k3, k4 = st.columns(4)
        cart(k1, L("MAPE médio", "Average MAPE"),
             f"{i18n.num(np.nanmean(z), 1)}%",
             L(f"{len(bt)} previsões em {erro.shape[0]} safras",
               f"{len(bt)} forecasts across {erro.shape[0]} vintages"))
        vies = np.nanmean(erro.to_numpy(float))
        cart(k2, L("Viés médio", "Average bias"),
             ("+" if vies > 0 else "") + f"{i18n.num(vies, 1)}%",
             L("positivo = o modelo previu a mais",
               "positive = the model over-forecast"))
        ult = erro.abs()[ate].dropna() if ate in erro.columns else pd.Series(dtype=float)
        cart(k3, L(f"MAPE em M{ate}", f"MAPE at M{ate}"),
             f"{i18n.num(ult.mean(), 1)}%" if len(ult) else "—",
             L("o mês mais distante desta visão",
               "the furthest month in this view"))
        pior = erro.abs().mean(axis=1).idxmax()
        cart(k4, L("Safra mais difícil", "Hardest vintage"), str(pior),
             L(f"erro médio de {i18n.num(erro.abs().mean(axis=1).max(), 1)}%",
               f"average error of "
               f"{i18n.num(erro.abs().mean(axis=1).max(), 1)}%"))

        st.divider()
        st.markdown(L("##### E o simulador de safra nova?",
                      "##### And the new-vintage simulator?"))
        b0 = backtest[(backtest["origem"] == -1)
                      & (backtest["metrica"] == col_total)
                      & (backtest["safra"].isin(safras))]
        if not b0.empty:
            mape0 = b0["erro_pct"].abs().mean()
            m12_0 = b0[b0["m"] == 12]["erro_pct"].abs().mean()
            st.caption(L(
                f"A matriz acima é previsão de um mês por vez, com histórico. "
                f"O simulador da outra aba é o caso oposto: uma safra que ainda "
                f"não existe, sem nenhum mês fechado, projetada até M12 de uma "
                f"vez só. Rodando o mesmo backtest nesse regime o erro é de "
                f"**{i18n.num(mape0, 1)}%** em média e "
                f"**{i18n.num(m12_0, 1)}%** em M12 — bem "
                f"maior, e é o que se espera de uma projeção que não tem em que "
                f"se apoiar. O número fica aqui para o simulador ser usado "
                f"sabendo disso.",
                f"The matrix above is a one-month-at-a-time forecast, with "
                f"history. The simulator in the other tab is the opposite "
                f"case: a vintage that doesn't exist yet, with no closed "
                f"month, projected to M12 in one go. Running the same backtest "
                f"in that regime the error is **{mape0:.1f}%** on average and "
                f"**{m12_0:.1f}%** at M12 — much larger, as expected from a "
                f"projection with nothing to lean on. The number stays here so "
                f"the simulator is used knowing that."))

        with st.expander(L("Ver previsto contra realizado",
                           "See forecast against actual")):
            comp = bt.pivot(index="safra", columns="m",
                            values=["previsto", "realizado"])
            st.dataframe(comp.round(2), use_container_width=True)

# ------------------------------------------------------------- SIMULADOR ----
with abas[3]:
    m_info = meta["por_corte"][corte]
    bg = BGNBD(); bg.params_ = m_info["bgnbd"]
    gg = GammaGamma(); gg.params_ = m_info["gamma_gamma"]

    st.markdown(L("#### Uma safra que ainda não aconteceu",
                  "#### A vintage that hasn't happened yet"))
    st.caption(L("Cliente novo não tem histórico, então a previsão usa a forma "
                 "incondicional do BG/NBD. O único parâmetro de negócio é o "
                 "ticket da 1ª compra.",
                 "A new customer has no history, so the forecast uses the "
                 "unconditional form of BG/NBD. The only business lever is "
                 "the 1st-purchase ticket."))

    s1, s2 = st.columns([0.42, 0.58])
    with s1:
        base_m0 = float(m_info["ticket_m0_medio"])
        ticket_m0 = st.slider(L("Ticket médio da **1ª compra**",
                                "Average ticket of the **1st purchase**"),
                              float(round(base_m0 * 0.4)),
                              float(round(base_m0 * 2.2)),
                              step=10.0, key="sim_tm0",
                              help=L(f"Média histórica: R$ {i18n.num(base_m0)}",
                                     f"Historical average: "
                                     f"R$ {i18n.num(base_m0)}"))
        n_cli = st.number_input(L("Clientes na safra", "Customers in the vintage"),
                                50, 20000, step=50, key="sim_ncli")
        elast = st.slider(L("Elasticidade do ticket de recompra",
                            "Repeat-ticket elasticity"), 0.0, 1.0,
                          step=0.01, key="sim_elast",
                          help=L("0 = o ticket de entrada não diz nada sobre a "
                                 "recompra. 1 = repasse proporcional. O valor "
                                 "padrão é o estimado nos dados.",
                                 "0 = the entry ticket says nothing about the "
                                 "repeat purchase. 1 = proportional "
                                 "pass-through. The default is the value "
                                 "estimated from the data."))
        sim = sim_curva
        if not mostrar_sim:
            st.caption(L("Marque **Incluir a safra simulada nos gráficos** na "
                         "barra lateral para ver esta safra entrando nas barras "
                         "e nas linhas da aba Safras.",
                         "Tick **Include the simulated vintage in the charts** "
                         "in the sidebar to see this vintage enter the bars "
                         "and lines of the Vintages tab."))

        # o M0 nao e o ticket da 1a compra: e o 1o MES de vida, que ja inclui
        # as recompras que acontecem dentro dele. Sem isso escrito, o numero do
        # grafico parece nao bater com o slider.
        l0 = sim[sim["m"] == 0].iloc[0]
        rep0 = float(l0["freq"]) - 1.0
        r0 = i18n.num(rep0, 2)
        tr0, rc0 = (i18n.num(l0['ticket_recompra_previsto']),
                    i18n.num(l0['rec_cliente']))
        st.info(L(
            f"**O M0 não é o ticket da 1ª compra.** M0 é o primeiro *mês* de "
            f"vida, e o modelo espera {r0} recompra dentro dele:\n\n"
            f"R$ {i18n.num(ticket_m0)} (1ª compra) + {r0} × "
            f"R$ {tr0} (recompra) = **R$ {rc0} por cliente em M0**",
            f"**M0 is not the 1st-purchase ticket.** M0 is the first *month* "
            f"of life, and the model expects {r0} repeat purchases within "
            f"it:\n\n"
            f"R$ {i18n.num(ticket_m0)} (1st purchase) + {r0} × "
            f"R$ {tr0} (repeat) = **R$ {rc0} per customer at M0**"))
        st.markdown("")
        for k in [3, 6, 12]:
            linha = sim[sim["m"] == k].iloc[0]
            st.markdown(
                f"<div class='cart' style='margin-bottom:8px'>"
                f"<div class='rot'>M{k}</div>"
                f"<div class='val'>R$ {i18n.num(linha['rec_cliente'])} "
                + L("por cliente", "per customer") + "</div>"
                f"<div class='sub'>{i18n.num(linha['freq'], 2)} "
                + L("compras · ticket médio", "purchases · average ticket")
                + f" R$ {i18n.num(linha['ticket'])} · "
                + L("receita total", "total revenue")
                + f" R$ {i18n.num(linha['rec_acum'])}</div></div>",
                unsafe_allow_html=True)
    with s2:
        fechadas = agg_todas[(agg_todas["frac_observada"] > 0.999)
                             & (agg_todas["m"] == 12)]["safra"]
        st.plotly_chart(
            G.curva_simulada(sim, agg_todas, "rec_cliente", list(fechadas),
                             formato),
            use_container_width=True, theme=None)
        st.caption(L(
            f"A faixa azul é o intervalo das {len(fechadas)} safras que já "
            "fecharam os 13 meses. Se a curva simulada sai da faixa, o cenário "
            "está pedindo algo que a base nunca entregou.",
            f"The blue band is the range of the {len(fechadas)} vintages that "
            "have already closed all 13 months. If the simulated curve leaves "
            "the band, the scenario is asking for something the base never "
            "delivered."))

    st.divider()
    el = i18n.num(m_info['elasticidade_ticket'], 2)
    st.caption(L(
        f"A elasticidade que liga o slider de ticket à previsão de recompra "
        f"vale {el} e foi estimada nos dados. "
        f"Ela é um acréscimo desta versão — a entrega original não tinha "
        f"alavanca de ticket, e por isso não tinha essa pergunta. De onde ela "
        f"sai está na aba **O case**.",
        f"The elasticity linking the ticket slider to the repeat-purchase "
        f"forecast is {el} and was estimated from the data. It's an addition "
        f"in this version — the original delivery had no ticket lever, and so "
        f"didn't have this question. Where it comes from is in the **The "
        f"case** tab."))

# ------------------------------------------------------------------ CASE ----
with abas[4]:
    st.markdown(ler_md("metodologia.md")
                .format(**{
                    "n_clientes": i18n.num(m_info['n_clientes']),
                    "elast": i18n.num(m_info['elasticidade_ticket'], 2),
                    "r2": i18n.num(m_info['elasticidade_r2'], 2),
                }))
    st.markdown(L("##### Os parâmetros são estáveis entre cortes?",
                  "##### Are the parameters stable across cutoffs?"))
    st.markdown(L(
        "Um jeito direto de conferir se o modelo é confiável: refazer a conta "
        "em datas diferentes e ver se ela dá respostas parecidas. Cada linha "
        "abaixo é o modelo ajustado até uma data de corte diferente. Se os "
        "números pulassem muito de uma linha para a outra, seria sinal de que "
        "o modelo está sendo levado pelo ruído do período e não pelo "
        "comportamento real dos clientes.",
        "A direct way to check whether the model is reliable: redo the math "
        "at different dates and see if it gives similar answers. Each row "
        "below is the model fitted up to a different cutoff date. If the "
        "numbers jumped a lot from one row to the next, it would be a sign "
        "that the model is being driven by the period's noise and not by the "
        "customers' real behavior."))
    est = pd.DataFrame([{
        L("Corte", "Cutoff"): mes_pt(c),
        L("Clientes", "Customers"): meta["por_corte"][c]["n_clientes"],
        "r": meta["por_corte"][c]["bgnbd"]["r"],
        "α": meta["por_corte"][c]["bgnbd"]["alpha"],
        "a": meta["por_corte"][c]["bgnbd"]["a"],
        "b": meta["por_corte"][c]["bgnbd"]["b"],
        "r/α": (meta["por_corte"][c]["bgnbd"]["r"]
                / meta["por_corte"][c]["bgnbd"]["alpha"]),
        "a/(a+b)": (meta["por_corte"][c]["bgnbd"]["a"]
                    / (meta["por_corte"][c]["bgnbd"]["a"]
                       + meta["por_corte"][c]["bgnbd"]["b"])),
        "corr(freq,ticket)": meta["por_corte"][c]["corr_freq_ticket"],
    } for c in CORTES]).set_index(L("Corte", "Cutoff"))
    st.dataframe(est.round(3), use_container_width=True)
    st.caption(L(
        "As colunas que valem a leitura são as duas razões, não os parâmetros "
        "crus. **r/α** é quantas compras por mês o cliente médio faz e "
        "**a/(a+b)** é a chance de ele sumir depois de cada compra — essas "
        "duas têm significado de negócio, e são bem mais estáveis entre os "
        "cortes do que r, α, a e b separados (é comum dois pares diferentes "
        "de números levarem à mesma razão). A última coluna é o teste do "
        "Gamma-Gamma: ele só vale se quem compra mais não tiver "
        "sistematicamente um ticket diferente de quem compra menos, e o "
        "critério usual é ficar abaixo de 0,1.",
        "The columns worth reading are the two ratios, not the raw "
        "parameters. **r/α** is how many purchases per month the average "
        "customer makes and **a/(a+b)** is the chance they drop out after "
        "each purchase — these two have business meaning, and are much more "
        "stable across cutoffs than r, α, a and b separately (two different "
        "pairs of numbers often lead to the same ratio). The last column is "
        "the Gamma-Gamma test: it only holds if those who buy more don't "
        "systematically have a different ticket from those who buy less, and "
        "the usual criterion is staying below 0.1."))

# ------------------------------------------------------------- GLOSSARIO ----
with abas[5]:
    st.markdown(L("#### O que cada termo quer dizer aqui",
                  "#### What each term means here"))
    st.markdown(ler_md("glossario.md"))

# ------------------------------------------------------------------ CASE ----
with abas[6]:
    texto = ler_md("case.md")
    antes, _, depois = texto.partition("<!-- GRAFICO_ELASTICIDADE -->")
    st.markdown(antes)

    e1, e2 = st.columns([0.58, 0.42])
    with e1:
        st.plotly_chart(
            G.dispersao_elasticidade(elast_cli,
                                     float(m_info["elasticidade_ticket"]),
                                     float(m_info["elasticidade_r2"])),
            use_container_width=True, theme=None)
    with e2:
        el = i18n.num(m_info['elasticidade_ticket'], 2)
        st.markdown(L(
            f"""Cada ponto é um cliente: ticket da 1ª compra no eixo x, ticket
médio das recompras no eixo y, ambos em log.

No nível da safra esse mesmo coeficiente oscilava entre −0,03 e 0,69 conforme o
corte — são só 23 médias, e média de safra é um número ruidoso. No nível do
cliente são milhares de pontos e ele fica em
**{el}** em todos os cortes. Por isso a
estimativa é feita no cliente, mesmo o uso sendo em safra.""",
            f"""Each point is a customer: 1st-purchase ticket on the x axis,
average repeat-purchase ticket on the y axis, both in log.

At the vintage level this same coefficient swung between −0.03 and 0.69
depending on the cutoff — there are only 23 averages, and a vintage average is
a noisy number. At the customer level there are thousands of points and it
stays at **{el}** across every cutoff. That's why the estimate is made at the
customer level, even though it's used at the vintage level."""))

    st.markdown(depois)
