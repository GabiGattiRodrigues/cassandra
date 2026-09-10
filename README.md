# Cassandra

**Quanto uma safra de clientes vai valer em M3, M6 e M12** — modelos de Customer
Lifetime Value (BG/NBD + Gamma-Gamma) numa leitura de cohort onde o realizado e a
previsão convivem no mesmo gráfico, e uma safra que ainda não existe pode ser
simulada.

🔗 **App:** https://cassandra-clv.streamlit.app
📊 **Base:** [Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) (UCI) — varejo online UK, 2009–2011

<p align="center"><img src="app/assets/cassandra.svg" width="520"></p>

---

## O problema

Quando aquisição pede orçamento para trazer 500 clientes novos, a pergunta que
decide o investimento não é quanto eles gastaram na primeira compra — é **quanto
eles vão ter gastado em 12 meses**. Um dashboard de realizado responde isso com
um ano de atraso.

Aqui a data de corte é um controle: arrastá-la para trás faz safras inteiras
saírem do realizado e entrarem na previsão. As safras antigas mostram o que
aconteceu; as recentes, o que o modelo espera; e a safra que ainda nem existe
pode ser simulada.

## Por que BG/NBD + Gamma-Gamma

O negócio é **não-contratual**: o cliente não cancela assinatura, ele só some.
Não existe evento de churn para rotular, então não há alvo para treinar um
classificador. A família BTYD modela o processo que gera as compras em vez do
rótulo que não existe:

- **BG/NBD** — enquanto ativo, o cliente compra a uma taxa λ ~ Gamma(r, α); após
  cada compra abandona com probabilidade p ~ Beta(a, b). Devolve compras
  esperadas em t meses e P(ainda vivo).
- **Gamma-Gamma** — o ticket individual varia em torno de uma média própria, que
  por sua vez varia entre clientes. Quem tem muito histórico é previsto pelo
  próprio ticket; quem tem pouco é puxado para a média da base.

Receita futura = compras esperadas × ticket esperado.

## O que tem de diferente aqui

**Os modelos são escritos do zero** (`app/modelo/btyd.py`), em numpy + scipy. A
lib `lifetimes`, o caminho usual, está sem manutenção desde 2020 e quebra com
versões recentes de pandas/scipy — dependência frágil num app que precisa ficar
de pé. Verossimilhança, fórmulas fechadas com a hipergeométrica gaussiana e
ajuste por MLE estão explícitos e testados.

**A validação é por recuperação de parâmetros.** `tests/test_btyd.py` simula
clientes a partir do processo gerador com parâmetros conhecidos, ajusta o modelo
e confere se os números voltam; também confere se a fórmula fechada de E[X(t)]
bate com a média de 20 mil clientes simulados (erro < 1,5%). É o teste que pega
erro de sinal e de constante — coisas que um MAPE bonito esconde.

**As decisões de dados estão no app, não escondidas:**

| Decisão | Por quê |
|---|---|
| Safra 2009-12 descartada | Censura à esquerda: a base começa em 01/12/2009, então quem já era cliente antes aparece como novo. 951 clientes (3× a média) com frequência M12 de 9,4 contra 3,9 das demais. Deixá-los dentro inflava a previsão de safra nova em 12%. |
| Calibração mínima de 15 meses | Com 12 meses o BG/NBD não identifica o churn: `b` estourava para ~97 (ninguém nunca abandona) e M12 vinha inflado. |
| Elasticidade do ticket no nível do cliente | No nível da safra sobram ~23 médias ruidosas e o coeficiente oscilava entre -0,03 e 0,69. No nível do cliente fica estável em 0,44 em todos os cortes. |
| M_k por aniversário do cliente | M_k = primeiros (k+1) meses de vida daquele cliente, não mês de calendário — quem entrou dia 30 não ganha um M0 de um dia. |

## Resultado

| | Erro |
|---|---|
| MAPE médio | **3,7%** |
| MAPE em M12 | 1,8% |
| Viés médio | −0,1% |

Validação cruzada por safra: para cada safra o modelo é reajustado **sem nenhum
cliente dela**, e cada mês é previsto com o anterior já fechado — com M0–M2
prevê o M3, com M0–M3 prevê o M4. Cada safra entra até onde já fechou, então são
21 safras em M1 e 10 em M12, num total de 186 previsões. O erro cai conforme a
safra amadurece: 5,2% em M1, 2,7% em M6, 1,8% em M12.

O simulador de safra nova é o caso oposto — sem nenhum mês fechado, projetando
até M12 de uma vez — e erra 18,2% em média. Está medido e exposto no app.

## Limites

- O modelo não sabe de campanha, preço nem sazonalidade — ele extrapola o padrão
  de compra observado.
- A elasticidade do ticket tem R² de 0,25. Por isso o slider fica exposto no
  app: dá para testar a premissa em vez de engolir o número.
- Base de varejo online do Reino Unido, 2009–2011, em libras exibidas como R$. O
  que se transfere é o método, não os patamares.

## Rodando local

```bash
pip install -r requirements.txt

python prep/00_baixar.py          # baixa o xlsx da UCI (44 MB)
python prep/01_load.py            # junta as duas abas
python prep/02_clean_cohorts.py   # limpeza + painel de safras
python prep/03_precompute.py      # ajusta os modelos e grava os painéis
python prep/05_backtest_safra.py  # validação cruzada por safra

python tests/test_btyd.py         # recuperação de parâmetros
python tests/test_graficos.py     # smoke test dos gráficos + conferência das pilhas

streamlit run app/app.py
```

Os `.parquet` em `app/dados/` já vêm prontos no repositório (1,5 MB), então o app
sobe sem rodar o `prep/`. O `prep/` está aqui para o pipeline ser auditável.

## Estrutura

```
app/
  app.py                 layout, filtros, abas
  graficos.py            os gráficos em Plotly
  tema.py                paleta validada p/ daltonismo e contraste
  case.md                a aba "O case"
  metodologia.md         a aba "Como o modelo foi feito"
  glossario.md           a aba "Glossário" — conceitos e contas em português
  modelo/
    btyd.py              BG/NBD e Gamma-Gamma do zero
    safras.py            pipeline de cohort, MAPE e simulador
  dados/                 painéis pré-calculados (.parquet)
prep/                    pipeline reproduzível, do xlsx aos painéis
tests/                   validação dos modelos, dos gráficos e reconciliação
web/                     prévia estática (mesmos números, sem servidor)
```

## Por que a base não é a Olist

A Olist seria a escolha óbvia por ser brasileira, mas ~97% dos clientes dela
compram uma vez só — sem recompra o BG/NBD não tem o que estimar. A Online
Retail II tem **72% de clientes com recompra** e 6,2 compras por cliente em
média, que é o regime em que a família BTYD faz sentido.

---

Feito por [Gabi Gatti Rodrigues](https://linkedin.com/in/gabriela-gatti-rodrigues) ·
outros projetos: [DaVinci](https://github.com/GabiGattiRodrigues/teste_a_b_desenho) (desenho de teste A/B) ·
[Michelangelo](https://github.com/GabiGattiRodrigues/teste_a_b_mensuracao) (mensuração) ·
[Dashboard Inteligente](https://dashboardinteligente.streamlit.app)
