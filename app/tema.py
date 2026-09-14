"""Paleta e chrome dos graficos. Todas as escalas foram validadas para
daltonismo e contraste antes de entrar aqui."""

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_MUDA = "#898781"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"

# rampa azul ordinal - os 4 marcos do ciclo de vida (M0 -> M12).
# escuro = inicio da vida do cliente, claro = cauda.
# validada: monotona em luminosidade, hue unico, ponta clara 2.06:1 vs fundo.
MARCOS_COR = {
    "M0":     "#0d366b",
    "M0→M3":  "#256abf",
    "M3→M6":  "#5598e7",
    "M6→M12": "#86b6ef",
}

# categorica de 8, em ordem fixa (nunca ciclar) - usada para comparar safras
# no grafico de linhas. validada: pior par adjacente dE 9.1 (CVD) / 19.6 (normal).
CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
              "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

# faixas do heatmap de MAPE - rampa azul, claro = erro baixo.
FAIXAS_MAPE = [
    (0, 5, "#cde2fb", "Até 5% — no alvo"),
    (5, 10, "#86b6ef", "5% a 10% — erro baixo"),
    (10, 20, "#2a78d6", "10% a 20% — dá pra planejar"),
    (20, 1e9, "#0d366b", "Acima de 20% — não usar sozinho"),
]

AZUL = "#2a78d6"
AZUL_ESC = "#0d366b"

# textura que marca "previsto" (encoding secundario, alem da cor mais clara)
HACHURA = "/"

LAYOUT = dict(
    # titulo encostado no topo da margem; a legenda vai para a direita, na
    # mesma faixa. se as duas ficarem a esquerda uma escreve por cima da outra
    # assim que o titulo passa de meia dezena de palavras.
    title_x=0, title_xanchor="left", title_y=1.0, title_yanchor="top",
    title_pad=dict(t=10, b=0),
    paper_bgcolor=SUPERFICIE,
    plot_bgcolor=SUPERFICIE,
    font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif',
              size=13, color=TINTA_2),
    margin=dict(l=58, r=16, t=74, b=46),
    hoverlabel=dict(bgcolor="white", font_size=13, bordercolor=EIXO),
    legend=dict(orientation="h", yanchor="bottom", y=1.0,
                xanchor="right", x=1, title_text=""),
    xaxis=dict(showgrid=False, linecolor=EIXO, ticks="outside",
               tickcolor=EIXO, tickfont=dict(color=TINTA_MUDA)),
    yaxis=dict(gridcolor=GRADE, zerolinecolor=EIXO, linecolor="rgba(0,0,0,0)",
               tickfont=dict(color=TINTA_MUDA)),
)


def cor_da_faixa(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "#f4f3ef"
    if v != v:
        return "#f4f3ef"
    for lo, hi, cor, _ in FAIXAS_MAPE:
        if lo <= v < hi:
            return cor
    return FAIXAS_MAPE[-1][2]


def tinta_sobre(cor_hex):
    """Preto ou branco, o que tiver mais contraste sobre a cor de fundo."""
    h = cor_hex.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    return "#0b0b0b" if lum > 0.42 else "#ffffff"
