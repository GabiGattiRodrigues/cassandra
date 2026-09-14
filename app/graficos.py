"""Os quatro graficos do dashboard, em Plotly.

Regra de leitura que vale para todos: cor cheia = ja aconteceu,
cor mais clara com hachura = previsao do modelo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import tema as T


def _fmt(v, formato):
    try:
        return formato.format(v)
    except Exception:
        return f"{v:,.0f}"


def _clarear(hex_cor, f=0.55):
    h = hex_cor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (int(c + (252 - c) * f) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# --------------------------------------------------------------------------- #
def barras_empilhadas(seg: pd.DataFrame, formato="R$ {:,.0f}",
                      titulo="Acumulado por safra"):
    """
    Uma barra por safra. De baixo para cima: o M0, depois o que a safra somou
    ate M3, depois ate M6, depois ate M12. A altura total da barra e o
    acumulado em M12.

    A cor de cada pedaco e a mesma em todas as safras, entao da para comparar
    faixa por faixa na horizontal. Dentro de um pedaco, a parte cheia e o que
    ja aconteceu e a hachurada e a previsao - um pedaco pode ser metade e
    metade quando o corte cai no meio dele.
    """
    fig = go.Figure()
    safras = list(dict.fromkeys(seg["safra"]))
    segmentos = ["M0", "M0→M3", "M3→M6", "M6→M12"]
    d = seg.set_index(["safra", "segmento"])
    total = seg.groupby("safra")["delta"].sum()

    for nome in segmentos:
        cor = T.MARCOS_COR[nome]
        # realizado embaixo, previsto logo acima: e a ordem cronologica
        for tipo, chave in [("realizado", "delta_realizado"),
                            ("previsto", "delta_previsto")]:
            vals, custom = [], []
            for s in safras:
                v = float(d.loc[(s, nome), chave]) if (s, nome) in d.index else 0.0
                vals.append(v)
                custom.append([nome, _fmt(float(total.get(s, 0)), formato)])
            if not any(v > 0 for v in vals):
                continue
            fig.add_bar(
                x=safras, y=vals, name=f"{nome} · {tipo}", width=0.7,
                customdata=custom, showlegend=False,
                marker=dict(
                    color=cor if tipo == "realizado" else _clarear(cor, 0.6),
                    line=dict(color=T.SUPERFICIE, width=1.5),
                    pattern=dict(shape="" if tipo == "realizado" else T.HACHURA,
                                 fgcolor=cor, size=5, solidity=0.32)),
                hovertemplate=("<b>safra %{x}</b><br>"
                               f"%{{customdata[0]}} · {tipo}: %{{y:,.0f}}<br>"
                               "total em M12: %{customdata[1]}<extra></extra>"),
            )

    # o acumulado final escrito em cima de cada barra
    fig.add_scatter(
        x=safras, y=[total.get(s, 0) for s in safras], mode="text",
        text=[_fmt(float(total.get(s, 0)), formato) for s in safras],
        textposition="top center", textfont=dict(size=10.5, color=T.TINTA_2),
        showlegend=False, hoverinfo="skip", cliponaxis=False,
    )

    layout = dict(T.LAYOUT)
    layout["margin"] = dict(l=58, r=34, t=52, b=46)   # folga p/ o rotulo da ponta
    fig.update_layout(
        **layout, barmode="stack", bargap=0.3,
        title=dict(text=titulo, font=dict(size=15, color=T.TINTA)),
        height=470,
    )
    # type="category" e obrigatorio: "2010-12" e lido como data pelo plotly, e
    # num eixo de datas a largura 0.7 vira 0.7 milissegundo (barra invisivel).
    fig.update_xaxes(type="category", tickfont=dict(size=11, color=T.TINTA_MUDA))
    fig.update_yaxes(range=[0, float(total.max()) * 1.12] if len(total) else None)
    return fig


# --------------------------------------------------------------------------- #
def barras_camadas(agg: pd.DataFrame, coluna: str, formato="R$ {:,.0f}",
                   titulo="Nível por marco"):
    """
    Mesma leitura visual da barra empilhada, para metrica que NAO soma entre
    marcos - o ticket medio.

    O ticket de M12 nao e o de M0 mais um pedaco: e uma media que se move, e
    pode ate cair. Entao em vez de empilhar deltas (que seria mentira grafica),
    cada marco e pintado como uma camada que vai de zero ate o NIVEL daquele
    marco, do M12 para o M0. O topo de cada faixa de cor e o ticket naquele
    marco, e a barra inteira e a curva do ticket vista de lado - inclusive
    quando ela desce.
    """
    marcos = [0, 3, 6, 12]
    rotulos = {0: "M0", 3: "M0→M3", 6: "M3→M6", 12: "M6→M12"}
    safras = sorted(agg["safra"].unique())
    fig = go.Figure()
    # do ultimo para o primeiro: a camada seguinte pinta por cima
    for k in reversed(marcos):
        d = agg[agg["m"] == k].set_index("safra").reindex(safras)
        cor = T.MARCOS_COR[rotulos[k]]
        obs = (d["frac_observada"] > 0.999).to_numpy()
        fig.add_bar(
            x=safras, y=d[coluna], width=0.7, name=f"M{k}", showlegend=False,
            marker=dict(
                color=[cor if o else _clarear(cor, 0.6) for o in obs],
                line=dict(color=T.SUPERFICIE, width=1.5),
                pattern=dict(shape=["" if o else T.HACHURA for o in obs],
                             fgcolor=cor, size=5, solidity=0.32)),
            hovertemplate="<b>safra %{x}</b> · nível em M" + str(k)
                          + "<br>%{y:,.0f}<extra></extra>",
        )
    # o rotulo vai acima do TOPO da barra, que nem sempre e o M12: quando o
    # ticket cai ao longo da vida, o nivel mais alto e um marco anterior
    d12 = agg[agg["m"] == 12].set_index("safra").reindex(safras)
    topos = (agg[agg["m"].isin(marcos)].groupby("safra")[coluna].max()
             .reindex(safras))
    fig.add_scatter(
        x=safras, y=topos, mode="text",
        text=[_fmt(v, formato) for v in d12[coluna]],
        textposition="top center", textfont=dict(size=10.5, color=T.TINTA_2),
        showlegend=False, hoverinfo="skip", cliponaxis=False)

    layout = dict(T.LAYOUT)
    layout["margin"] = dict(l=58, r=16, t=52, b=46)
    fig.update_layout(
        **layout, barmode="overlay", bargap=0.3, height=470,
        title=dict(text=titulo, font=dict(size=15, color=T.TINTA)),
    )
    fig.update_xaxes(type="category",     # ver nota em barras_empilhadas
                     tickfont=dict(size=11, color=T.TINTA_MUDA))
    topo = float(agg[agg["m"].isin(marcos)][coluna].max())
    fig.update_yaxes(range=[0, topo * 1.12])
    return fig


# --------------------------------------------------------------------------- #
def linhas_por_safra(agg: pd.DataFrame, coluna: str, safras: list[str],
                     formato="R$ {:,.0f}", titulo="Curva de vida por safra"):
    """
    Uma linha por safra, x = M0..M12. Trecho solido = realizado;
    trecho tracejado = previsao. Rotulo direto no fim de cada linha.
    """
    fig = go.Figure()
    for i, s in enumerate(safras[:8]):
        d = agg[agg["safra"] == s].sort_values("m")
        if d.empty:
            continue
        cor = T.CATEGORICA[i % len(T.CATEGORICA)]
        obs = d["frac_observada"].to_numpy() > 0.999
        corte = int(obs.sum())

        # realizado
        fig.add_scatter(
            x=d["m"][:corte], y=d[coluna][:corte], mode="lines+markers",
            name=s, legendgroup=s, line=dict(color=cor, width=2),
            marker=dict(size=7, color=cor,
                        line=dict(color=T.SUPERFICIE, width=2)),
            hovertemplate=f"<b>{s}</b> · M%{{x}}<br>realizado: "
                          "%{y:,.0f}<extra></extra>",
        )
        # previsto (comeca no ultimo ponto realizado para nao dar buraco)
        if corte < len(d):
            ini = max(corte - 1, 0)
            fig.add_scatter(
                x=d["m"][ini:], y=d[coluna][ini:], mode="lines",
                name=f"{s} (previsto)", legendgroup=s, showlegend=False,
                line=dict(color=cor, width=2, dash="dot"), opacity=0.75,
                hovertemplate=f"<b>{s}</b> · M%{{x}}<br>previsto: "
                              "%{y:,.0f}<extra></extra>",
            )
        # rotulo direto na ponta
        fig.add_scatter(
            x=[d["m"].iloc[-1]], y=[d[coluna].iloc[-1]], mode="text",
            text=[f"  {s}"], textposition="middle right",
            textfont=dict(color=T.TINTA_2, size=11),
            showlegend=False, hoverinfo="skip",
        )

    fig.add_annotation(x=1, y=-0.16, xref="paper", yref="paper",
                       showarrow=False, xanchor="right",
                       text="linha cheia = realizado · pontilhada = previsão",
                       font=dict(size=11, color=T.TINTA_MUDA))
    fig.update_layout(
        **T.LAYOUT, hovermode="x unified", height=440,
        title=dict(text=titulo, font=dict(size=15, color=T.TINTA)),
    )
    fig.update_xaxes(tickmode="array", tickvals=list(range(13)),
                     ticktext=[f"M{k}" for k in range(13)],
                     range=[-0.4, 13.4])
    return fig


# --------------------------------------------------------------------------- #
def barras_comparando_safras(agg: pd.DataFrame, m: int, coluna: str,
                             formato="R$ {:,.0f}", coluna_real: str | None = None):
    """
    Um M fixo, uma barra por safra - para achar a melhor e a pior safra.

    Em M0 a barra mostra so o realizado: o primeiro mes de vida de qualquer
    safra que ja existe ja aconteceu, entao previsao ali seria ruido de
    arredondamento em cima de um numero que a base ja tem fechado.
    """
    d = agg[agg["m"] == m].sort_values("safra")
    so_realizado = (m == 0) and coluna_real is not None
    if so_realizado:
        valores = d[coluna_real].to_numpy()
        realizado = pd.Series(True, index=d.index)
    else:
        valores = d[coluna].to_numpy()
        realizado = d["frac_observada"] > 0.999

    fig = go.Figure()
    for rotulo, mask in [("Realizado", realizado), ("Previsto", ~realizado)]:
        if not mask.any():
            continue
        cor = T.AZUL_ESC if rotulo == "Realizado" else _clarear(T.AZUL_ESC)
        fig.add_bar(
            x=d["safra"][mask.to_numpy()], y=valores[mask.to_numpy()],
            name=rotulo,
            marker=dict(color=cor, line=dict(color=T.SUPERFICIE, width=2),
                        pattern=dict(shape="" if rotulo == "Realizado" else T.HACHURA,
                                     fgcolor=T.AZUL_ESC, size=5, solidity=0.28)),
            text=[_fmt(v, formato) for v in valores[mask.to_numpy()]],
            textposition="outside", textfont=dict(size=11, color=T.TINTA_2),
            cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>" + rotulo.lower()
                          + ": %{y:,.0f}<extra></extra>",
        )
    media = float(np.nanmean(valores)) if len(valores) else 0
    fig.add_hline(y=media, line=dict(color=T.TINTA_MUDA, width=1, dash="dash"),
                  annotation_text=f"média {_fmt(media, formato)}",
                  annotation_position="top left",
                  annotation_font=dict(size=11, color=T.TINTA_MUDA))
    fig.update_layout(
        **T.LAYOUT, height=420, bargap=0.3,
        title=dict(text=(f"{'Acumulado até' if coluna != 'ticket' else 'Nível em'}"
                         f" M{m}, safra a safra"),
                   font=dict(size=15, color=T.TINTA)),
    )
    fig.update_xaxes(type="category")     # ver nota em barras_empilhadas
    return fig


# --------------------------------------------------------------------------- #
def matriz_mape(mape: pd.DataFrame, vies: pd.DataFrame | None = None,
                rot_col=None, titulo=None,
                nome_col="mês", extra=None, rot_extra="viés",
                extra2=None, rot_extra2=None, extra3=None, rot_extra3=None,
                margens=False, rot_margem="média", sub_col=None):
    """
    Matriz safra x (mes ou corte) com o erro da previsao. Cada celula traz o
    numero escrito - a cor e reforco, nunca a unica informacao.

    Eixos numericos com rotulo customizado de proposito: rotulo tipo "2011-02"
    ou "fev/11" e lido como data pelo plotly, o que desalinha as celulas do
    fundo em relacao aos retangulos desenhados por cima.
    """
    if rot_col is None:
        # as colunas de margem sao texto e nao levam o prefixo "M"
        rot_col = lambda c: f"M{c}" if isinstance(c, (int, np.integer)) else str(c)

    m = mape.dropna(how="all").dropna(axis=1, how="all")
    if m.empty:
        return None

    n_lin, n_col = m.shape
    if margens:
        # media da linha na ultima coluna e media da coluna na ultima linha,
        # separadas por uma coluna/linha vazia para nao parecerem mais uma safra
        m = m.copy()
        med_lin = m.mean(axis=1, skipna=True)
        m[" "] = np.nan
        m[rot_margem] = med_lin
        rodape = m.iloc[:n_lin, :].mean(axis=0, skipna=True)
        m.loc[" "] = np.nan
        m.loc[rot_margem] = rodape
        m.loc[rot_margem, rot_margem] = m.iloc[:n_lin, :n_col].to_numpy(float)[
            ~np.isnan(m.iloc[:n_lin, :n_col].to_numpy(float))].mean()

    z = m.to_numpy(float)
    ny, nx = z.shape
    e_margem = lambda i, j: (margens and (i >= n_lin or j >= n_col))
    cores = [[T.cor_da_faixa(v) for v in linha] for linha in z]
    y_pos = lambda i: ny - 1 - i          # primeira safra no topo

    fig = go.Figure()
    for i in range(ny):
        for j in range(nx):
            v = z[i, j]
            if v != v:
                continue
            c = cores[i][j]
            mg = e_margem(i, j)
            fig.add_shape(type="rect", x0=j - .46, x1=j + .46,
                          y0=y_pos(i) - .46, y1=y_pos(i) + .46,
                          fillcolor=T.SUPERFICIE if mg else c,
                          line=dict(color=T.GRADE if mg else T.SUPERFICIE,
                                    width=2 if mg else 2),
                          layer="below")
            fig.add_annotation(
                x=j, y=y_pos(i), text=f"{v:.1f}%" if mg else f"{v:.0f}%",
                showarrow=False,
                font=dict(size=11, color=T.TINTA if mg else T.tinta_sobre(c),
                          weight="bold" if mg else "normal"))

    def _mat(df):
        if df is None:
            return np.full((ny, nx), np.nan)
        return df.reindex(index=m.index, columns=m.columns).to_numpy(float)

    linhas_rot = np.tile(np.array(list(m.index), dtype=object)[:, None], (1, nx))
    cols_rot = np.tile(np.array([rot_col(c) for c in m.columns],
                                dtype=object)[None, :], (ny, 1))
    cd = np.dstack([_mat(vies), _mat(extra), linhas_rot, cols_rot,
                    _mat(extra2), _mat(extra3)])

    # camada invisivel so para o hover, nas MESMAS posicoes dos retangulos
    fig.add_heatmap(
        z=z[::-1], x=list(range(nx)), y=[y_pos(i) for i in range(ny)][::-1],
        showscale=False, opacity=0, customdata=cd[::-1],
        hovertemplate=("safra <b>%{customdata[2]}</b> · " + nome_col
                       + " %{customdata[3]}<br>"
                       "erro absoluto: %{z:.1f}%<br>"
                       "viés: %{customdata[0]:+.1f}% (positivo = previu a mais)"
                       + ("<br>" + rot_extra + ": %{customdata[1]:.0f}"
                          if extra is not None else "")
                       + ("<br>" + str(rot_extra2) + ": %{customdata[4]:.1f}%"
                          if extra2 is not None else "")
                       + ("<br>" + str(rot_extra3) + ": %{customdata[5]:.1f}%"
                          if extra3 is not None else "")
                       + "<extra></extra>"),
    )

    layout = dict(T.LAYOUT)
    # o eixo x fica no topo e mora dentro da margem superior, junto com o
    # titulo. quando o rotulo tem subtitulo ele ocupa duas linhas, entao a
    # margem precisa caber titulo + duas linhas, senao um escreve por cima
    # do outro.
    topo = 104 if sub_col else 76
    layout["margin"] = dict(l=76, r=16, t=topo, b=16)
    fig.update_layout(
        **layout, height=50 + topo + 34 * ny,
        title=dict(text=titulo or "Erro da previsão (MAPE) por safra e mês",
                   font=dict(size=15, color=T.TINTA),
                   y=1.0, yanchor="top", pad=dict(t=14, b=0)),
    )
    # o rotulo da coluna pode carregar um subtitulo (ex.: quantas safras
    # entram naquele mes), em fonte menor na linha de baixo
    def _tick(c):
        r = rot_col(c)
        if sub_col and c in sub_col:
            return f"{r}<br><span style='font-size:9.5px'>{sub_col[c]}</span>"
        return r

    fig.update_xaxes(tickmode="array", tickvals=list(range(nx)),
                     ticktext=[_tick(c) for c in m.columns],
                     side="top", showgrid=False, zeroline=False,
                     linecolor="rgba(0,0,0,0)", range=[-.6, nx - .4],
                     tickfont=dict(size=11))
    fig.update_yaxes(tickmode="array",
                     tickvals=[y_pos(i) for i in range(ny)],
                     ticktext=list(m.index), showgrid=False, zeroline=False,
                     linecolor="rgba(0,0,0,0)", range=[-.6, ny - .4],
                     tickfont=dict(size=11))
    return fig


# --------------------------------------------------------------------------- #
def curva_simulada(sim: pd.DataFrame, agg_real: pd.DataFrame, coluna: str,
                   safras_ref: list[str], formato="R$ {:,.0f}"):
    """A safra simulada contra a faixa das safras reais ja observadas."""
    ref = agg_real[agg_real["safra"].isin(safras_ref)]
    faixa = ref.groupby("m")[coluna].agg(["min", "max", "median"]).reset_index()

    fig = go.Figure()
    fig.add_scatter(x=faixa["m"], y=faixa["max"], mode="lines",
                    line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=faixa["m"], y=faixa["min"], mode="lines",
                    line=dict(width=0), fill="tonexty",
                    fillcolor="rgba(42,120,214,0.13)",
                    name="faixa das safras reais",
                    hovertemplate="M%{x}<br>piso das safras reais: "
                                  "%{y:,.0f}<extra></extra>")
    fig.add_scatter(x=faixa["m"], y=faixa["median"], mode="lines",
                    line=dict(color=T.AZUL, width=2, dash="dash"),
                    name="mediana das safras reais",
                    hovertemplate="M%{x}<br>mediana real: %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=sim["m"], y=sim[coluna], mode="lines+markers",
                    line=dict(color=T.AZUL_ESC, width=3),
                    marker=dict(size=8, color=T.AZUL_ESC,
                                line=dict(color=T.SUPERFICIE, width=2)),
                    name="safra simulada",
                    hovertemplate="M%{x}<br>simulado: %{y:,.0f}<extra></extra>")
    lay = dict(T.LAYOUT)
    # esta figura mora numa coluna estreita: a legenda quebra em duas linhas,
    # entao a margem de cima tem que caber titulo + duas linhas de legenda
    lay["margin"] = dict(l=58, r=16, t=106, b=46)
    fig.update_layout(
        **lay, height=440, hovermode="x unified",
        title=dict(text="Safra simulada contra o histórico",
                   font=dict(size=15, color=T.TINTA)),
    )
    fig.update_xaxes(tickmode="array", tickvals=list(range(13)),
                     ticktext=[f"M{k}" for k in range(13)])
    return fig


def dispersao_elasticidade(cli_tab: pd.DataFrame, beta: float, r2: float):
    """Ticket da 1a compra x ticket de recompra, no nivel do cliente."""
    d = cli_tab
    fig = go.Figure()
    fig.add_scatter(x=d["ticket_m0"], y=d["ticket_recompra"], mode="markers",
                    marker=dict(size=5, color=T.AZUL, opacity=0.35,
                                line=dict(width=0)),
                    name="clientes",
                    hovertemplate="1ª compra: %{x:,.0f}<br>"
                                  "recompra média: %{y:,.0f}<extra></extra>")
    xs = np.geomspace(max(d["ticket_m0"].min(), 1), d["ticket_m0"].max(), 60)
    alpha = np.log(d["ticket_recompra"]).mean() - beta * np.log(d["ticket_m0"]).mean()
    fig.add_scatter(x=xs, y=np.exp(alpha) * xs ** beta, mode="lines",
                    line=dict(color=T.AZUL_ESC, width=2.5),
                    name=f"ajuste: elasticidade {beta:.2f} (R²={r2:.2f})",
                    hoverinfo="skip")
    fig.update_layout(**T.LAYOUT, height=380,
                      title=dict(text="Ticket de entrada × ticket de recompra",
                                 font=dict(size=15, color=T.TINTA)))
    fig.update_xaxes(type="log", title="ticket da 1ª compra (log)",
                     title_font=dict(size=12, color=T.TINTA_MUDA))
    fig.update_yaxes(type="log", title="ticket médio das recompras (log)",
                     title_font=dict(size=12, color=T.TINTA_MUDA))
    return fig
