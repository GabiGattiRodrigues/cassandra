"""
Português e inglês na mesma tela.

O texto em inglês mora ao lado do português (`L("Safras", "Vintages")`), a
língua fica no session_state e espelha na URL (`?lang=en`), e o número não
muda de língua -- muda só o separador (1.234,5 vira 1,234.5).
"""

from __future__ import annotations

import streamlit as st

IDIOMAS = ("pt", "en")
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]
MESES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def idioma() -> str:
    try:
        return st.session_state.get("idioma", "pt")
    except Exception:           # fora do Streamlit (testes): português
        return "pt"


def en() -> bool:
    return idioma() == "en"


def L(pt, en_):
    """A frase na língua ativa. As duas versões ficam lado a lado no código."""
    return en_ if en() else pt


def iniciar() -> None:
    """Lê ?lang=en na primeira execução da sessão."""
    if "idioma" not in st.session_state:
        pedido = str(st.query_params.get("lang", "pt")).lower()
        st.session_state["idioma"] = "en" if pedido.startswith("en") else "pt"


def _trocar() -> None:
    novo = st.session_state.get("_seletor_idioma")
    # clicar de novo na língua ativa desmarca o controle: não é pedido de troca
    if novo in IDIOMAS:
        st.session_state["idioma"] = novo
        st.query_params["lang"] = novo


def seletor() -> None:
    """O botão PT/EN."""
    st.session_state["_seletor_idioma"] = idioma()
    st.segmented_control(
        "Idioma · Language", options=list(IDIOMAS),
        format_func=lambda k: {"pt": "🇧🇷 Português", "en": "🇺🇸 English"}[k],
        key="_seletor_idioma", on_change=_trocar,
        label_visibility="collapsed", selection_mode="single")


def num(x: float, casas: int = 0) -> str:
    s = f"{x:,.{casas}f}"
    if en():
        return s
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def fmt(formato: str, v: float) -> str:
    """Aplica um formato do tipo 'R$ {:,.0f}' e troca o separador pela língua."""
    s = formato.format(v)
    if en():
        return s
    return s.replace(",", "@").replace(".", ",").replace("@", ".")
