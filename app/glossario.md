Cada termo abaixo aparece em algum lugar do app. A ideia é que dê para ler o
projeto inteiro sem conhecer a literatura de CLV antes — então tudo aqui está
escrito em português comum, e o nome técnico vem junto só para você reconhecer
quando ele aparecer em outro lugar.

**Se for ler só um parágrafo, leia este.** O app pega os clientes que fizeram a
primeira compra no mesmo mês, chama esse grupo de **safra**, e acompanha quanto
esse grupo comprou mês a mês desde a primeira compra. Onde a base já tem o dado,
o número é contagem: aconteceu. Onde ainda não tem, entra um modelo que estima o
que provavelmente vai acontecer. O app deixa claro, o tempo todo, qual dos dois
você está olhando.

---

### A leitura de safra

**Safra (ou *cohort*).** O grupo de clientes que fez a primeira compra no mesmo
mês. A safra 2010-03 são todas as pessoas cuja compra inicial caiu em março de
2010. Uma vez na safra, sempre na safra — o cliente não muda de grupo depois.

*Por que agrupar assim:* clientes de meses diferentes estão em momentos
diferentes da vida deles. Comparar um cliente de dois anos com um de dois meses
não diz nada; comparar dois clientes no mesmo mês de vida diz muito.

**M0, M1, … M12.** Os meses de vida do cliente, contados a partir da **primeira
compra dele**, não do calendário. M0 é o primeiro mês de vida, M3 são os
primeiros 4 meses, M12 são 13 meses.

*Por que não usar mês do calendário:* quem entrou no dia 30 teria um M0 de um
dia só, e a comparação entre safras ficaria torta. Aqui o M0 de quem entrou dia
30 vai até o dia 29 do mês seguinte.

**Acumulado.** Todo número de M_k conta desde a primeira compra, não só o que
aconteceu naquele mês. A receita em M6 já inclui a de M0 a M5. É por isso que a
curva de receita nunca desce.

**Realizado × previsto.** *Realizado* é contagem direta na base: aconteceu, está
registrado. *Previsto* é o que o modelo espera para o pedaço que ainda não
aconteceu. No app, **cor cheia = realizado, hachura = previsto** — e uma mesma
barra pode ter os dois, quando a data de corte cai no meio daquele pedaço.

**Data de corte.** O "hoje" da simulação. Tudo até ela é realizado; dali para
frente é o modelo. Arrastar o corte para trás faz safras inteiras saírem do
realizado e entrarem na previsão — é o jeito de ver o modelo sendo testado
contra um passado que você já conhece.

---

### As três métricas

**Frequência de compra.** Quantas compras o cliente fez, em média, acumulado até
aquele mês.

`frequência = total de compras da safra ÷ nº de clientes`

Uma safra com frequência 3,9 em M12 comprou, em média, 3,9 vezes nos 13
primeiros meses de vida.

**Ticket médio.** Quanto vale uma compra, em média.

`ticket = receita total ÷ nº de compras`

É a única das três que **não é acumulável**: o ticket de M12 não é o de M0 mais
um pedaço, é uma média que se move conforme entram compras novas — e pode cair.

**Receita por cliente.** O produto das duas: `frequência × ticket`, ou, o que dá
no mesmo, `receita total ÷ nº de clientes`. É a métrica que responde "quanto
vale um cliente desta safra", e é a que o time financeiro usa para decidir
quanto vale a pena pagar para adquirir um cliente novo.

**LTV / CLV (valor do cliente ao longo da vida).** É a receita por cliente
olhada como projeto: quanto aquele cliente vai gerar no total. Aqui ela é
truncada em 13 meses, porque é o horizonte que a base permite **conferir**. LTV
"infinito" existe na teoria, mas é um número que ninguém consegue verificar.

---

### O modelo, em português

**Negócio não-contratual.** O cliente não cancela nada: ele simplesmente para de
comprar, e você nunca fica sabendo. Não existe uma data de churn para registrar.

Isso tem uma consequência prática grande: **não dá para treinar um modelo de
churn**, porque não existe o rótulo "este cliente saiu" para o modelo aprender.
A saída é outra — em vez de prever um rótulo que não existe, modelar o
comportamento que gera as compras. É para isso que existe a família **BTYD**
(*Buy Till You Die*, "compre até morrer").

**BG/NBD** — responde **quantas compras** esperar. A ideia é simples de contar:
cada cliente tem um ritmo próprio de compra e uma teimosia própria para
continuar ou sumir. Nenhum dos dois é observável direto. O modelo supõe que
esses dois traços variam entre as pessoas seguindo uma distribuição conhecida,
olha o histórico de todo mundo junto e descobre o formato dessas distribuições.
Com isso em mãos, ele consegue dizer quantas compras esperar de cada cliente
daqui para frente.

- **r e α** descrevem o ritmo de compra. **r/α** é a taxa média da base — aqui
  ≈ 0,25, ou uma compra a cada 4 meses. O **r** sozinho diz o quanto os clientes
  diferem entre si: r baixo significa base muito heterogênea.
- **a e b** descrevem o abandono. **a/(a+b)** é a chance média de o cliente
  sumir depois de cada compra — aqui ≈ 5%.

**Gamma-Gamma** — responde **a que valor** essas compras acontecem. Supõe que o
ticket de cada cliente varia em torno de uma média própria dele, e que essa
média varia entre clientes. Na prática o resultado é uma média ponderada
sensata: quem já tem muito histórico é previsto pelo próprio ticket; quem tem
pouco é puxado para a média da base, porque com duas compras não dá para
confiar que aquele valor é mesmo o dele.

**x, t_x e T.** Os três números que resumem cada cliente para o BG/NBD.

- **x** = quantas compras repetidas ele fez (a primeira não conta, ela é a
  aquisição);
- **t_x** = quanto tempo passou entre a primeira e a última compra;
- **T** = há quanto tempo ele é cliente, até a data de corte.

Cliente com x alto e t_x perto de T está comprando até agora. Cliente com x alto
e t_x baixo comprou muito e sumiu.

**P(vivo).** A probabilidade de o cliente ainda estar ativo, dado o que ele fez.
Não é observável — é o que o modelo deduz. Quem tinha ritmo e parou há muito
tempo tem P(vivo) baixo.

**Previsão condicional × incondicional.** *Condicional* é a previsão de um
cliente **que já tem histórico**: usa o x, o t_x e o T dele. *Incondicional* é a
de um cliente que ainda não existe — não há em que se apoiar, então a previsão
sai só dos parâmetros do modelo e do tempo. O simulador de safra nova é esse
segundo caso, e é por isso que o erro dele é maior.

**Verossimilhança e máxima verossimilhança.** Verossimilhança é a chance de o
modelo, com um dado conjunto de parâmetros, ter gerado exatamente o histórico
que você observou. Maximizar a verossimilhança é procurar os parâmetros que
tornam o que aconteceu o mais provável possível. **Não é um menu de valores para
testar** — é uma conta de otimização com uma resposta só, dada a base e a janela.

---

### As premissas e os diagnósticos

**Elasticidade do ticket.** Responde uma pergunta prática: *se a safra entra com
um ticket de primeira compra mais alto, quanto disso se mantém nas recompras?*

A resposta não é um multiplicador, é um expoente:

`ticket_recompra = ticket_recompra_médio × (ticket_M0 ÷ ticket_M0_médio) ^ elasticidade`

- elasticidade **1** = repasse proporcional. Dobrou a entrada, dobra a recompra.
- elasticidade **0** = o ticket de entrada não diz nada sobre a recompra.
- elasticidade **0,44** (o valor estimado aqui) = dobrou a entrada, a recompra
  sobe 2^0,44 = **1,36×**, não 2×.

Ela é estimada por uma regressão no nível do cliente: o ticket da 1ª compra no
eixo x, o ticket médio das recompras no eixo y, os dois em logaritmo. Em escala
logarítmica o coeficiente da reta já *é* a elasticidade — essa é a razão de usar
log, e não uma decisão estética.

**Regressão à média.** É o fenômeno por trás dessa elasticidade menor que 1. Quem
teve uma primeira compra excepcionalmente alta teve, em parte, sorte — e sorte
não se repete. Na compra seguinte a pessoa tende a voltar para perto da média. É
o mesmo mecanismo que o Gamma-Gamma aplica quando puxa o cliente de pouco
histórico na direção da média da base.

**Correlação frequência × ticket.** O Gamma-Gamma só vale se quem compra mais
não tiver, sistematicamente, um ticket diferente de quem compra menos. O
critério usual é |correlação| < 0,1. Aqui fica em torno de 0,05 — a hipótese
passa, e o número está na barra lateral justamente para poder ser conferido em
vez de presumido.

**Censura à esquerda.** Acontece quando a base começa depois do negócio. Quem já
era cliente antes aparece como se tivesse sido adquirido no primeiro mês da
base — não é cliente novo, é cliente antigo com o histórico cortado. Aqui isso
atingiu a safra 2009-12, que tinha frequência 9,4 em M12 contra 3,9 das outras.
Por isso ela foi removida.

---

### Como o erro é medido

**MAPE (erro percentual médio absoluto).** O erro percentual médio, sem sinal:
`|previsto − realizado| ÷ realizado`, tirada a média. MAPE de 4% quer dizer que
a previsão erra 4% para cima ou para baixo, em média. Não diz para qual lado.

**Viés.** O mesmo erro, mas **com** sinal: `(previsto − realizado) ÷ realizado`.
Viés positivo quer dizer que o modelo prevê a mais de forma sistemática.

*Por que os dois aparecem juntos:* um MAPE de 5% com viés de +5% é bem pior que
um MAPE de 5% com viés de 0%. O primeiro erra sempre para o mesmo lado, e erro
que sempre vai para o mesmo lado se acumula no orçamento.

**Fora da amostra (*out-of-sample*).** Medir erro nos mesmos dados usados para
ajustar o modelo não mede nada — o modelo já viu a resposta. Erro fora da
amostra é medido em dados que o ajuste nunca viu.

**Vazamento (*leakage*).** Quando informação do teste escapa para o treino sem
querer. A forma mais comum e mais discreta: escolher a especificação do modelo
olhando o resultado do mesmo teste que você depois vai reportar. O número sai
bonito e não vale nada.

**Validação cruzada por safra (*leave-one-cohort-out*).** É como o erro é medido
aqui. Para avaliar a safra 2010-03, o modelo é reajustado **sem nenhum cliente
dela** — o ajuste nunca vê a safra que vai prever. Depois ele projeta a vida
dela e compara com o que de fato aconteceu. E isso se repete safra por safra.

**Previsão um passo à frente.** O regime usado na aba de qualidade: cada mês é
previsto com o mês anterior já fechado. Com M0, M1 e M2 na mão, prevê-se o M3;
quando o M3 fecha, prevê-se o M4. É como uma curva de safra é acompanhada na
prática, e é a razão de o erro ficar em 3,7% — bem abaixo dos 18% de projetar 13
meses de uma vez, sem nenhum histórico.
