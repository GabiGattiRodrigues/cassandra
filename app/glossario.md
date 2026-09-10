Cada termo abaixo aparece em algum lugar do app. A ideia é que dê para ler o
projeto inteiro sem precisar conhecer a literatura de CLV antes.

---

### A leitura de safra

**Safra (ou cohort).** O grupo de clientes que fez a primeira compra no mesmo
mês. A safra 2010-03 são todas as pessoas cuja compra inicial caiu em março de
2010. Uma vez na safra, sempre na safra — o cliente não muda de grupo depois.

**M0, M1, … M12.** Meses de vida do cliente, contados a partir da **primeira
compra dele**, não do calendário. M0 é o primeiro mês de vida, M3 são os
primeiros 4 meses, M12 são 13 meses. Quem entrou dia 30 tem o M0 dele indo até
o dia 29 do mês seguinte — se fosse mês de calendário, esse cliente teria um M0
de um dia só e a comparação entre safras ficaria torta.

**Acumulado.** Todo número de M_k é acumulado desde a primeira compra, não o
que aconteceu só naquele mês. A receita em M6 inclui a de M0 a M5. É por isso
que a curva de receita nunca desce.

**Realizado × previsto.** Realizado é contagem direta na base: aconteceu, está
registrado. Previsto é o que o modelo espera para o pedaço que ainda não
aconteceu. No app, **cor cheia = realizado, hachura = previsto** — e uma mesma
barra pode ter os dois, quando a data de corte cai no meio daquele pedaço.

**Data de corte.** O "hoje" da simulação. Tudo até ela é realizado; dali para
frente é o modelo. Arrastar o corte para trás faz safras inteiras saírem do
realizado e entrarem na previsão.

---

### As três métricas

**Frequência de compra.** Quantas compras o cliente fez, em média, acumulado
até aquele mês. `frequência = total de compras da safra ÷ nº de clientes`. Uma
safra com frequência 3,9 em M12 comprou, em média, 3,9 vezes nos 13 primeiros
meses.

**Ticket médio.** Quanto vale uma compra, em média.
`ticket = receita total ÷ nº de compras`. É a única das três métricas que **não
é acumulável**: o ticket de M12 não é o de M0 mais um pedaço, é uma média que se
move conforme entram compras novas — e pode cair.

**Receita por cliente.** O produto das duas: `frequência × ticket`, ou
`receita total ÷ nº de clientes`. É a métrica que responde "quanto vale um
cliente desta safra", e é a que o time financeiro usa para decidir quanto pagar
para adquirir um cliente novo.

**LTV / CLV (Customer Lifetime Value).** Valor do cliente ao longo da vida —
aqui truncado em 13 meses, porque é o horizonte que a base permite validar. LTV
"infinito" existe na teoria, mas é um número que ninguém consegue conferir.

---

### O modelo

**Negócio não-contratual.** O cliente não cancela nada: ele simplesmente para de
comprar, e você nunca fica sabendo. Não existe evento de churn com data. Isso
elimina a possibilidade de treinar um classificador de churn — não há rótulo
para aprender. A família BTYD (*Buy Till You Die*) existe justamente para esse
caso: em vez de prever o rótulo que não existe, ela modela o processo que gera
as compras.

**BG/NBD (Beta-Geometric / Negative Binomial Distribution).** Modela **quantas
compras** esperar. Cada cliente tem duas características que nunca observamos:
uma taxa própria de compra (λ) e uma probabilidade própria de abandonar (p).
O modelo supõe que λ vem de uma distribuição Gamma(r, α) e p de uma Beta(a, b),
estima esses quatro números a partir do histórico de todo mundo, e daí devolve
quantas compras esperar de cada cliente.

- **r e α** descrevem a taxa de compra. **r/α** é a taxa média de compra por
  mês da base (aqui ≈ 0,25, ou uma compra a cada 4 meses). O **r** sozinho diz
  o quanto os clientes diferem entre si: r baixo = base muito heterogênea.
- **a e b** descrevem o abandono. **a/(a+b)** é a chance média de o cliente
  abandonar depois de cada compra (aqui ≈ 5%).

**Gamma-Gamma.** Modela **a que valor** essas compras acontecem. Supõe que o
ticket de cada cliente varia em torno de uma média própria dele, e que essa
média varia entre clientes. O resultado prático é uma média ponderada: quem tem
muito histórico é previsto pelo próprio ticket, quem tem pouco é puxado para a
média da base. Os parâmetros são **p, q, v**.

**x, t_x e T.** Os três números que resumem cada cliente para o BG/NBD.
**x** = quantas compras repetidas ele fez (a primeira não conta, ela é a
aquisição). **t_x** = tempo entre a primeira e a última compra. **T** = idade do
cliente na data de corte. Cliente com x alto e t_x perto de T está comprando
até agora; cliente com x alto e t_x baixo comprou muito e sumiu.

**P(vivo).** A probabilidade de o cliente ainda estar ativo, dado o que ele fez.
Não é observável — é o que o BG/NBD deduz. Quem tinha ritmo e parou há muito
tempo tem P(vivo) baixo.

**Previsão condicional × incondicional.** *Condicional* é a previsão de um
cliente **com** histórico: usa o x, t_x e T dele. *Incondicional* é a de um
cliente que ainda não existe — não há em que condicionar, então a previsão usa
só os parâmetros do modelo e o tempo. O simulador de safra nova é o caso
incondicional.

**Verossimilhança e máxima verossimilhança (MLE).** A verossimilhança é a
probabilidade de o modelo, com um dado conjunto de parâmetros, ter gerado
exatamente o histórico observado. Maximizar a verossimilhança é procurar os
parâmetros que tornam o que aconteceu o mais provável possível. **Não é um grid
de valores para testar** — é uma otimização com uma resposta só, dada a base e a
janela.

---

### As premissas e os diagnósticos

**Elasticidade do ticket.** Responde: *se a safra entra com um ticket de
primeira compra mais alto, quanto disso se mantém nas recompras?* É um expoente,
não um multiplicador:

`ticket_recompra = ticket_recompra_médio × (ticket_M0 ÷ ticket_M0_médio) ^ elasticidade`

- elasticidade **1** = repasse proporcional. Dobrou a entrada, dobra a recompra.
- elasticidade **0** = o ticket de entrada não diz nada sobre a recompra.
- elasticidade **0,44** (o valor estimado aqui) = dobrou a entrada, a recompra
  sobe 2^0,44 = **1,36×**, não 2×.

Ela é estimada por uma regressão log-log no nível do cliente: põe o ticket da 1ª
compra no eixo x, o ticket médio das recompras no eixo y, ambos em logaritmo, e
o coeficiente da reta é a elasticidade. Em log-log o coeficiente já *é* a
elasticidade — é a razão de usar log, e não uma decisão estética.

**Regressão à média.** O fenômeno por trás dessa elasticidade menor que 1. Quem
teve uma primeira compra excepcionalmente alta teve, em parte, sorte — e a sorte
não se repete. Na compra seguinte a pessoa tende a voltar para perto da média.
É o mesmo mecanismo que o Gamma-Gamma aplica no nível individual quando puxa o
cliente de pouco histórico na direção da média da base.

**Correlação frequência × ticket.** O Gamma-Gamma exige que quem compra mais
não tenha, sistematicamente, um ticket diferente de quem compra menos. O
critério usual é |correlação| < 0,1. Aqui fica em torno de 0,05 — a hipótese
passa, e o número está na barra lateral para poder ser conferido em vez de
presumido.

**Censura à esquerda.** Quando a base começa depois de o negócio começar, quem
já era cliente aparece como se tivesse sido adquirido no primeiro mês da base.
Não é cliente novo — é cliente antigo com histórico cortado. Aqui isso atingiu a
safra 2009-12, que tinha frequência 9,4 em M12 contra 3,9 das outras, e por isso
ela foi removida.

---

### Como o erro é medido

**MAPE (Mean Absolute Percentage Error).** Erro percentual médio, sem sinal:
`|previsto − realizado| ÷ realizado`, tirada a média. MAPE de 4% quer dizer que
a previsão erra 4% para cima ou para baixo, em média. Não diz a direção.

**Viés.** O mesmo erro, **com** sinal: `(previsto − realizado) ÷ realizado`.
Viés positivo = o modelo prevê a mais de forma sistemática. Um MAPE de 5% com
viés de +5% é bem pior que um MAPE de 5% com viés de 0% — o primeiro erra sempre
para o mesmo lado, e erro sistemático se acumula no orçamento. Por isso os dois
aparecem juntos no app.

**Fora da amostra (out-of-sample).** Medir erro nos mesmos dados usados para
ajustar o modelo não mede nada: o modelo já viu a resposta. Erro fora da amostra
é medido em dados que o ajuste nunca viu.

**Vazamento (leakage).** Quando informação do teste escapa para o treino sem
querer. A forma mais comum e mais discreta: escolher a especificação do modelo
olhando o resultado do mesmo holdout que depois se reporta. O número sai bonito
e não vale nada.

**Validação cruzada por safra (*leave-one-cohort-out*).** Como o erro é medido
aqui. Para avaliar a safra 2010-03, o modelo é reajustado **sem nenhum cliente
dela** — o ajuste nunca vê a safra que vai prever. Depois ele projeta a vida
dela e compara com o que de fato aconteceu. Repete-se isso safra por safra.

**Previsão um passo à frente.** O regime usado na aba de qualidade: cada mês é
previsto com o mês anterior já fechado. Com M0, M1 e M2 na mão prevê-se o M3;
quando o M3 fecha, prevê-se o M4. É como uma curva de cohort é acompanhada na
prática, e é a razão de o erro ficar em 3,7% — bem abaixo dos 18% de projetar 13
meses de uma vez, sem nenhum histórico.
