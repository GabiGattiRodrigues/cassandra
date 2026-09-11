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
import tema as T
from modelo.btyd import BGNBD, GammaGamma
from modelo.safras import (METRICAS, agregar_por_safra, mape_por_mes,
                           segmentos_marcos, simular_safra)

AQUI = pathlib.Path(__file__).resolve().parent
DADOS = AQUI / "dados"

st.set_page_config(page_title="Cassandra · previsão de safras",
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


MES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
          "jul", "ago", "set", "out", "nov", "dez"]


def mes_pt(d):
    """strftime usa o locale C e devolve 'Feb'; aqui o rótulo sai em português."""
    d = pd.Timestamp(d)
    return f"{MES_PT[d.month - 1]}/{d.year % 100:02d}"


def plot(fig):
    """theme=None: o Streamlit reescreve barmode e legenda quando aplica o tema
    dele por cima. Os gráficos aqui já vêm com paleta e layout próprios."""
    st.plotly_chart(fig, use_container_width=True, theme=None)


painel, meta, elast_cli, backtest = carregar()
CORTES = meta["cortes"]
ULTIMO = CORTES[-1]

# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🔮 Cassandra")
    st.caption("Previsão de ticket, frequência e receita por safra")
    st.divider()

    st.markdown("**Data de corte**")
    st.caption("Tudo até aqui é realizado. Daqui pra frente, é o modelo falando.")
    corte = st.select_slider(" ", options=CORTES, value=ULTIMO,
                             format_func=mes_pt,
                             label_visibility="collapsed")

    metrica_nome = st.selectbox("Métrica", list(METRICAS.keys()))
    col_total, col_real, formato, acumulavel = METRICAS[metrica_nome]

    st.divider()
    st.markdown("**Recortes**")
    tipos_all = sorted(painel["tipo_cliente"].dropna().unique().tolist())
    regioes_all = sorted(painel["regiao"].dropna().unique().tolist())
    tipos = st.multiselect("Tipo de cliente (faixa de ticket na 1ª compra)",
                           tipos_all, default=tipos_all)
    regioes = st.multiselect("Região", regioes_all, default=regioes_all)
    if not tipos:
        tipos = tipos_all
    if not regioes:
        regioes = regioes_all

    safras_all = sorted(painel["safra"].dropna().unique().tolist())
    ini, fim = st.select_slider(
        "Safras na visão", options=safras_all,
        value=(safras_all[0], safras_all[-1]),
        help="Menos safras = gráfico mais legível. A conta não muda.")

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
        "Incluir a safra simulada nos gráficos", value=False,
        help="A safra que você monta na aba 'Simular safra nova' entra como "
             "mais uma barra, toda hachurada — ela é 100% previsão.")

    st.markdown("**Modelo ajustado neste corte**")
    st.markdown(
        f"<span class='tag'>r {m_info['bgnbd']['r']:.3f}</span>"
        f"<span class='tag'>α {m_info['bgnbd']['alpha']:.3f}</span>"
        f"<span class='tag'>a {m_info['bgnbd']['a']:.3f}</span>"
        f"<span class='tag'>b {m_info['bgnbd']['b']:.3f}</span>",
        unsafe_allow_html=True)
    st.caption(f"{m_info['n_clientes']:,} clientes · "
               f"{m_info['pct_repetidores']:.0%} com recompra · "
               f"corr(freq,ticket) = {m_info['corr_freq_ticket']:+.3f}"
               .replace(",", "."))

agg_todas = agregado(corte, tuple(tipos), tuple(regioes))
agg = agg_todas[(agg_todas["safra"] >= ini) & (agg_todas["safra"] <= fim)].copy()

NOME_SIM = "Simulada"
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
    st.markdown(
        "**Quanto uma safra de clientes vai valer em M3, M6 e M12** — "
        "modelada com BG/NBD + Gamma-Gamma, com o realizado e o previsto "
        "no mesmo gráfico.")
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


cart(k1, "Safras na visão", f"{agg_reais['safra'].nunique()}",
     f"{alvo['clientes'].sum():,} clientes".replace(",", "."))
cart(k2, "Safras já fechadas em M12", f"{len(obs)}",
     "realizado completo, sem modelo")
cart(k3, "Safras em previsão", f"{len(prev)}",
     "M12 ainda não aconteceu")
if len(alvo):
    v = alvo["rec_acum"].sum() / max(alvo["clientes"].sum(), 1)
    vp = (prev["rec_acum"].sum() / max(prev["clientes"].sum(), 1)) if len(prev) else 0
    cart(k4, "Receita/cliente em M12", f"R$ {v:,.0f}".replace(",", "."),
         (f"safras em previsão: R$ {vp:,.0f}".replace(",", ".")) if vp else
         "todas realizadas")

st.markdown(
    f"<div class='nota'>Corte em <b>{pd.Timestamp(corte).strftime('%d/%m/%Y')}</b>. "
    "Barra cheia e linha sólida = o que já aconteceu. "
    "Barra hachurada e linha pontilhada = previsão do modelo.</div>",
    unsafe_allow_html=True)
st.write("")

# --------------------------------------------------------------------------- #
abas = st.tabs(["Safras", "Comparar um M", "Qualidade da previsão",
                "Simular safra nova", "Como o modelo foi feito", "Glossário",
                "O case"])

# ---------------------------------------------------------------- SAFRAS ----
with abas[0]:
    st.markdown(
        "<div class='leg'>"
        + "".join(f"<span><i style='background:{c}'></i>{n}</span>"
                  for n, c in T.MARCOS_COR.items())
        + "<span style='color:#898781'>│ hachura = previsto</span></div>",
        unsafe_allow_html=True)
    if acumulavel:
        seg = segmentos_marcos(agg, col_total, col_real)
        st.plotly_chart(
            G.barras_empilhadas(
                seg, formato,
                f"{metrica_nome} acumulada — M0, M3, M6 e M12 por safra"),
            use_container_width=True, theme=None)
        st.caption("Cada barra é uma safra. De baixo para cima: o M0, o que ela "
                   "somou até M3, até M6 e até M12 — a altura total é o "
                   "acumulado em M12. A cor de cada faixa é a mesma em todas "
                   "as safras, então dá para comparar faixa por faixa na "
                   "horizontal.")
    else:
        st.plotly_chart(
            G.barras_camadas(
                agg, col_total, formato,
                f"{metrica_nome} em cada marco, por safra"),
            use_container_width=True, theme=None)
        st.caption(
            "Ticket médio não é acumulável — o de M12 não é o de M0 mais um "
            "pedaço, é uma média que se move e pode até cair. Então cada faixa "
            "de cor vai de zero até o **nível** daquele marco: o topo de cada "
            "cor é o ticket ali, e a barra inteira é a curva do ticket vista "
            "de lado.")

    st.divider()
    padrao = safras[-6:] if len(safras) > 6 else safras
    sel = st.multiselect("Safras no gráfico de linhas (até 8)", safras,
                         default=padrao, max_selections=8)
    if sel:
        st.plotly_chart(
            G.linhas_por_safra(agg, col_total, sorted(sel), formato,
                               f"{metrica_nome} acumulada ao longo da vida"),
            use_container_width=True, theme=None)
    with st.expander("Ver os números"):
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

        st.caption("Fundo branco = **realizado**, já aconteceu na base. "
                   "Fundo azul em itálico = **previsto** pelo modelo.")
        st.dataframe(tab.style.apply(pintar, axis=None).format("{:,.2f}"),
                     use_container_width=True)

# ------------------------------------------------------------ COMPARAR M ----
with abas[1]:
    m_sel = st.select_slider("Mês de vida", options=list(range(13)), value=12,
                             format_func=lambda k: f"M{k}")
    st.plotly_chart(
        G.barras_comparando_safras(agg, m_sel, col_total, formato, col_real),
        use_container_width=True, theme=None)
    if m_sel == 0:
        st.caption("Em M0 a barra é só o realizado: o primeiro mês de vida de "
                   "qualquer safra que já existe já aconteceu, então não há o "
                   "que prever ali.")
    col_uso = col_real if m_sel == 0 else col_total
    d = agg[agg["m"] == m_sel].sort_values(col_uso, ascending=False)
    if len(d):
        c1, c2, c3 = st.columns(3)
        cart(c1, f"Melhor safra em M{m_sel}", d.iloc[0]["safra"],
             formato.format(d.iloc[0][col_uso]).replace(",", "."))
        cart(c2, f"Pior safra em M{m_sel}", d.iloc[-1]["safra"],
             formato.format(d.iloc[-1][col_uso]).replace(",", "."))
        espalh = d.iloc[0][col_uso] / max(d.iloc[-1][col_uso], 1e-9)
        cart(c3, "Distância entre elas", f"{espalh:.1f}×",
             "quanto a melhor rende sobre a pior")

# -------------------------------------------------------------- QUALIDADE ----
# Um passo a frente, sempre: com M0..M_{k-1} fechados da para prever o M_k, e so.
# Cada celula (safra, M_k) e uma previsao de um mes, feita com tudo que veio
# antes dela - a mesma leitura que se faz acompanhando a curva de um cohort.
# No backtest isso e a linha com origem = k-1.
with abas[2]:
    st.markdown("#### Quanto o modelo erra")
    st.caption(
        "Cada mês é previsto com o que veio antes dele: com M0, M1 e M2 "
        "fechados prevê-se o M3; quando o M3 fecha, prevê-se o M4. Uma previsão "
        "de um mês por vez, que é como a curva de um cohort é acompanhada. "
        "Para cada safra o modelo é reajustado **sem nenhum cliente dela** "
        "(validação cruzada por safra). Cada safra entra até onde ela já "
        "fechou: para pontuar o M3 basta ter o M3 fechado, não os 13 meses. "
        "Por isso a matriz tem mais safras nos meses baixos e vai afinando.")

    ate = st.radio("Até onde mostrar", [3, 6, 12], index=2, horizontal=True,
                   format_func=lambda k: f"até o M{k}")

    bt = backtest[(backtest["origem"] == backtest["m"] - 1)
                  & (backtest["m"] >= 1) & (backtest["m"] <= ate)
                  & (backtest["metrica"] == col_total)
                  & (backtest["safra"].isin(safras))].copy()
    n_por_mes = bt.groupby("m")["safra"].nunique().to_dict()

    if bt.empty:
        st.warning("Nenhuma safra fechada neste recorte.")
    else:
        erro = bt.pivot(index="safra", columns="m", values="erro_pct")
        st.markdown(
            "<div class='leg'>"
            + "".join(f"<span><i style='background:{c}'></i>{rot}</span>"
                      for _, _, c, rot in T.FAIXAS_MAPE)
            + "</div>", unsafe_allow_html=True)

        st.plotly_chart(
            G.matriz_mape(
                erro.abs(), erro, margens=True,
                titulo="Erro de cada mês, previsto com o mês anterior fechado",
                extra=bt.pivot(index="safra", columns="m", values="previsto"),
                rot_extra="previsto",
                extra2=bt.pivot(index="safra", columns="m", values="realizado"),
                rot_extra2="realizado",
                sub_col={k: f"{v} safras" for k, v in n_por_mes.items()}),
            use_container_width=True, theme=None)
        st.caption(
            "Abaixo de cada M está quantas safras já fecharam aquele mês — a "
            "matriz vai afinando para a direita porque safra recente ainda não "
            "chegou lá. A última coluna é o erro médio de cada safra; a última "
            "linha é o erro médio de cada mês. O M0 não aparece porque não "
            "existe mês fechado antes dele para servir de base.")

        z = erro.abs().to_numpy(float)
        k1, k2, k3, k4 = st.columns(4)
        cart(k1, "MAPE médio", f"{np.nanmean(z):.1f}%",
             f"{len(bt)} previsões em {erro.shape[0]} safras")
        cart(k2, "Viés médio", f"{np.nanmean(erro.to_numpy(float)):+.1f}%",
             "positivo = o modelo previu a mais")
        ult = erro.abs()[ate].dropna() if ate in erro.columns else pd.Series(dtype=float)
        cart(k3, f"MAPE em M{ate}", f"{ult.mean():.1f}%" if len(ult) else "—",
             "o mês mais distante desta visão")
        pior = erro.abs().mean(axis=1).idxmax()
        cart(k4, "Safra mais difícil", str(pior),
             f"erro médio de {erro.abs().mean(axis=1).max():.1f}%")

        st.divider()
        st.markdown("##### E o simulador de safra nova?")
        b0 = backtest[(backtest["origem"] == -1)
                      & (backtest["metrica"] == col_total)
                      & (backtest["safra"].isin(safras))]
        if not b0.empty:
            mape0 = b0["erro_pct"].abs().mean()
            m12_0 = b0[b0["m"] == 12]["erro_pct"].abs().mean()
            st.caption(
                f"A matriz acima é previsão de um mês por vez, com histórico. "
                f"O simulador da outra aba é o caso oposto: uma safra que ainda "
                f"não existe, sem nenhum mês fechado, projetada até M12 de uma "
                f"vez só. Rodando o mesmo backtest nesse regime o erro é de "
                f"**{mape0:.1f}%** em média e **{m12_0:.1f}%** em M12 — bem "
                f"maior, e é o que se espera de uma projeção que não tem em que "
                f"se apoiar. O número fica aqui para o simulador ser usado "
                f"sabendo disso.")

        with st.expander("Ver previsto contra realizado"):
            comp = bt.pivot(index="safra", columns="m",
                            values=["previsto", "realizado"])
            st.dataframe(comp.round(2), use_container_width=True)

# ------------------------------------------------------------- SIMULADOR ----
with abas[3]:
    m_info = meta["por_corte"][corte]
    bg = BGNBD(); bg.params_ = m_info["bgnbd"]
    gg = GammaGamma(); gg.params_ = m_info["gamma_gamma"]

    st.markdown("#### Uma safra que ainda não aconteceu")
    st.caption("Cliente novo não tem histórico, então a previsão usa a forma "
               "incondicional do BG/NBD. O único parâmetro de negócio é o "
               "ticket da 1ª compra.")

    s1, s2 = st.columns([0.42, 0.58])
    with s1:
        base_m0 = float(m_info["ticket_m0_medio"])
        ticket_m0 = st.slider("Ticket médio da **1ª compra**",
                              float(round(base_m0 * 0.4)),
                              float(round(base_m0 * 2.2)),
                              step=10.0, key="sim_tm0",
                              help=f"Média histórica: R$ {base_m0:,.0f}"
                                   .replace(",", "."))
        n_cli = st.number_input("Clientes na safra", 50, 20000, step=50,
                                key="sim_ncli")
        elast = st.slider("Elasticidade do ticket de recompra", 0.0, 1.0,
                          step=0.01, key="sim_elast",
                          help="0 = o ticket de entrada não diz nada sobre a "
                               "recompra. 1 = repasse proporcional. O valor "
                               "padrão é o estimado nos dados.")
        sim = sim_curva
        if not mostrar_sim:
            st.caption("Marque **Incluir a safra simulada nos gráficos** na "
                       "barra lateral para ver esta safra entrando nas barras "
                       "e nas linhas da aba Safras.")

        # o M0 nao e o ticket da 1a compra: e o 1o MES de vida, que ja inclui
        # as recompras que acontecem dentro dele. Sem isso escrito, o numero do
        # grafico parece nao bater com o slider.
        l0 = sim[sim["m"] == 0].iloc[0]
        rep0 = float(l0["freq"]) - 1.0
        st.info(
            f"**O M0 não é o ticket da 1ª compra.** M0 é o primeiro *mês* de "
            f"vida, e o modelo espera {rep0:.2f} recompra dentro dele:\n\n"
            f"R$ {ticket_m0:,.0f} (1ª compra) + {rep0:.2f} × "
            f"R$ {l0['ticket_recompra_previsto']:,.0f} (recompra) = "
            f"**R$ {l0['rec_cliente']:,.0f} por cliente em M0**"
            .replace(",", "."))
        st.markdown("")
        for k in [3, 6, 12]:
            linha = sim[sim["m"] == k].iloc[0]
            st.markdown(
                f"<div class='cart' style='margin-bottom:8px'>"
                f"<div class='rot'>M{k}</div>"
                f"<div class='val'>R$ {linha['rec_cliente']:,.0f} por cliente</div>"
                f"<div class='sub'>{linha['freq']:.2f} compras · ticket médio "
                f"R$ {linha['ticket']:,.0f} · receita total "
                f"R$ {linha['rec_acum']:,.0f}</div></div>".replace(",", "."),
                unsafe_allow_html=True)
    with s2:
        fechadas = agg_todas[(agg_todas["frac_observada"] > 0.999)
                             & (agg_todas["m"] == 12)]["safra"]
        st.plotly_chart(
            G.curva_simulada(sim, agg_todas, "rec_cliente", list(fechadas),
                             formato),
            use_container_width=True, theme=None)
        st.caption(
            f"A faixa azul é o intervalo das {len(fechadas)} safras que já "
            "fecharam os 13 meses. Se a curva simulada sai da faixa, o cenário "
            "está pedindo algo que a base nunca entregou.")

    st.divider()
    st.caption(
        f"A elasticidade que liga o slider de ticket à previsão de recompra "
        f"vale {m_info['elasticidade_ticket']:.2f} e foi estimada nos dados — "
        f"de onde ela sai está na aba **O case**.")

# ------------------------------------------------------------------ CASE ----
with abas[4]:
    st.markdown((AQUI / "metodologia.md").read_text(encoding="utf-8")
                .format(**{
                    "n_clientes": f"{m_info['n_clientes']:,}".replace(",", "."),
                    "elast": f"{m_info['elasticidade_ticket']:.2f}",
                    "r2": f"{m_info['elasticidade_r2']:.2f}",
                }))
    st.markdown("##### Os parâmetros são estáveis entre cortes?")
    st.markdown(
        "Um jeito direto de conferir se o modelo é confiável: refazer a conta "
        "em datas diferentes e ver se ela dá respostas parecidas. Cada linha "
        "abaixo é o modelo ajustado até uma data de corte diferente. Se os "
        "números pulassem muito de uma linha para a outra, seria sinal de que "
        "o modelo está sendo levado pelo ruído do período e não pelo "
        "comportamento real dos clientes.")
    est = pd.DataFrame([{
        "Corte": mes_pt(c),
        "Clientes": meta["por_corte"][c]["n_clientes"],
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
    } for c in CORTES]).set_index("Corte")
    st.dataframe(est.round(3), use_container_width=True)
    st.caption(
        "As colunas que valem a leitura são as duas razões, não os parâmetros "
        "crus. **r/α** é quantas compras por mês o cliente médio faz e "
        "**a/(a+b)** é a chance de ele sumir depois de cada compra — essas "
        "duas têm significado de negócio, e são bem mais estáveis entre os "
        "cortes do que r, α, a e b separados (é comum dois pares diferentes "
        "de números levarem à mesma razão). A última coluna é o teste do "
        "Gamma-Gamma: ele só vale se quem compra mais não tiver "
        "sistematicamente um ticket diferente de quem compra menos, e o "
        "critério usual é ficar abaixo de 0,1.")

# ------------------------------------------------------------- GLOSSARIO ----
with abas[5]:
    st.markdown("#### O que cada termo quer dizer aqui")
    st.markdown((AQUI / "glossario.md").read_text(encoding="utf-8"))

# ------------------------------------------------------------------ CASE ----
with abas[6]:
    texto = (AQUI / "case.md").read_text(encoding="utf-8")
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
        st.markdown(
            f"""Cada ponto é um cliente: ticket da 1ª compra no eixo x, ticket
médio das recompras no eixo y, ambos em log.

No nível da safra esse mesmo coeficiente oscilava entre −0,03 e 0,69 conforme o
corte — são só 23 médias, e média de safra é um número ruidoso. No nível do
cliente são milhares de pontos e ele fica em
**{m_info['elasticidade_ticket']:.2f}** em todos os cortes. Por isso a
estimativa é feita no cliente, mesmo o uso sendo em safra.""")

    st.markdown(depois)
