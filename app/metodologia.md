### A resposta curta

Os quatro parâmetros do BG/NBD (r, α, a, b) e os três do Gamma-Gamma (p, q, v)
**não são escolhidos** — são **estimados por máxima verossimilhança** em cima da
janela de calibração. Não existe grid de valores para testar: dada a base e a
janela, a otimização devolve um conjunto só, e ele é o que maximiza a
probabilidade de ter observado exatamente aquele histórico de compras.

O que *é* escolha do analista está na tabela abaixo — janela de calibração,
unidade de tempo, quem entra na base — e essas escolhas sim foram decididas por
erro fora da amostra, com uma ressalva que vale dizer em voz alta: escolher a
especificação olhando o mesmo holdout que você reporta é vazamento. Aqui cada
decisão só ficou de pé quando valia em todos os cortes de backtest, não no
melhor deles.

---

### O que é estimado e o que é escolhido

| | |
|---|---|
| **r, α** — BG/NBD, taxa de compra | **Estimado.** Descrevem a Gamma de onde sai o λ de cada cliente: r/α é a taxa média de compra da base, r sozinho diz o quanto os clientes diferem entre si. |
| **a, b** — BG/NBD, abandono | **Estimado.** Descrevem a Beta da probabilidade de o cliente abandonar depois de cada compra. a/(a+b) é a chance média de abandono por compra. |
| **p, q, v** — Gamma-Gamma | **Estimado.** Verossimilhança própria, ajustada só nos clientes com recompra — quem comprou uma vez só não tem ticket de recompra para informar nada. |
| Janela de calibração | **Escolha.** Mínimo de 15 meses. Com 12, b estourava para ~97 (equivale a dizer que ninguém nunca abandona) e M12 vinha inflado. Decidido por estabilidade dos parâmetros, não por MAPE. |
| Unidade de tempo | **Escolha.** Mês de 30,4375 dias. Não muda o ajuste — só deixa r/α e as previsões legíveis em meses em vez de dias. |
| Quem entra na base | **Escolha.** Safra 2009-12 fora, por censura à esquerda. Decidido por diagnóstico da própria safra (frequência 9,4 contra 3,9 das outras), não por tentativa e erro. |
| Elasticidade do ticket | **Estimada** por regressão log-log no nível do cliente, mas **exposta como controle** no simulador — é a premissa mais fraca do conjunto (R² {r2}) e quem usa merece poder mexer nela. |

---

### Como a estimação roda

Para cada cliente entram três números: `x` (compras repetidas), `t_x` (tempo
entre a 1ª e a última compra) e `T` (idade do cliente no corte). A
log-verossimilhança do BG/NBD soma esses três num termo fechado por cliente; o
otimizador procura os quatro parâmetros que maximizam a soma.

**Parâmetros otimizados em log.** Todos os quatro têm que ser positivos.
Otimizar log(r), log(α), log(a), log(b) garante isso sem precisar de restrição
na fronteira, onde o otimizador costuma travar.

**Três chutes iniciais, dois otimizadores.** Nelder-Mead primeiro, porque não
precisa de derivada e atravessa região plana; L-BFGS-B depois, para refinar. Os
três chutes existem para detectar ótimo local: se convergissem para pontos
diferentes, o resultado não seria confiável. Convergem para o mesmo.

**Somas em log-espaço.** O termo que separa "cliente vivo" de "cliente que
abandonou" soma duas exponenciais que estouram em float. Somar via log-sum-exp
evita o overflow — é o tipo de detalhe que não muda a matemática e quebra a
implementação.

---

### Como isso foi validado

**1. Recuperação de parâmetros.** Simula 4 mil clientes a partir do processo
gerador do BG/NBD com r, α, a, b conhecidos, ajusta o modelo em cima da
simulação e confere se os números voltam. E confere se a fórmula fechada de
E[X(t)], que usa a hipergeométrica gaussiana, bate com a média de 20 mil
clientes simulados — erro menor que 1,5% em t = 3, 6 e 12 meses. *Isso responde:
a implementação está certa?* É o teste que pega erro de sinal e de constante,
que um MAPE bonito esconde.

**2. Backtest com validação cruzada por safra.** Para cada safra que já fechou
os 13 meses, o modelo é reajustado **sem nenhum cliente dela** — o ajuste nunca
vê a safra que vai prever. Depois cada mês é previsto com o que veio antes dele:
com M0, M1 e M2 fechados prevê-se o M3; quando o M3 fecha, prevê-se o M4. Uma
previsão de um mês por vez, que é como a curva de um cohort é acompanhada de
verdade. *Isso responde: o modelo acerta neste negócio?*

| | Erro |
|---|---|
| MAPE médio | **3,7%** |
| MAPE em M12 | 1,8% |
| Viés médio | −0,1% |

São 186 previsões em 21 safras. Cada safra entra até onde já fechou — para
pontuar o M3 basta ter o M3 fechado, não os 13 meses —, então a matriz tem 21
safras em M1 e vai afinando até 10 em M12. O erro cai conforme a safra
amadurece: 5,2% em M1, 2,7% em M6, 1,8% em M12. Quanto mais histórico o cliente
acumulou, mais o BG/NBD tem em que se apoiar para prever o mês seguinte.

**O simulador de safra nova é o caso oposto** e merece o número dele: uma safra
que ainda não existe, sem nenhum mês fechado, projetada até M12 de uma vez só.
No mesmo backtest isso dá **18,2%** de erro médio e **23,3%** em M12. É bem
maior, é o esperado de uma projeção que não tem em que se apoiar, e está no app
para o simulador ser usado sabendo disso.

**3. Por que a validação é por safra, e não por data de corte.** O caminho
mais óbvio seria fixar uma data, ajustar até ali e projetar o futuro. Mas o
BG/NBD precisa de pelo menos 15 meses de calibração, e a base tem 24 — então o
primeiro corte possível é fev/2011, quando as safras que já fecharam os 13
meses **já tinham fechado**. Os primeiros meses de vida delas nunca foram
futuro em corte nenhum, e a matriz sairia pela metade. Deixar a safra de fora
do ajuste resolve isso sem inventar dado, e permite avaliar cada safra até onde
ela chegou em vez de descartar tudo que ainda não fechou os 13 meses.

A ressalva honesta: o ajuste usa dados de calendário posteriores ao período da
safra, vindos de outras safras. Um choque macro que atingisse toda a base
estaria parcialmente "conhecido". O que não acontece — e é o que importa — é o
modelo ver a própria safra que está prevendo.

---
