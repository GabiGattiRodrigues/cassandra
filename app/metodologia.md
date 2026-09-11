### A pergunta que esta aba responde

> *"Como você escolheu os parâmetros do modelo?"*

A resposta curta é: **eu não escolhi.** Quem calcula os parâmetros é o
computador, e ele não tem liberdade para chegar em outro resultado. O que eu
escolhi foi outra coisa — e está tudo separado e listado mais abaixo.

Se você não é da área, vale ler os dois blocos seguintes. Eles explicam, sem
fórmula, o que essa frase quer dizer.

---

### O que quer dizer "estimar" um parâmetro

Imagine que você tem o histórico de compras de {n_clientes} clientes e quer
resumir esse grupo em poucos números — basicamente dois: **com que frequência
essa gente costuma comprar** e **com que facilidade costuma sumir**.

Existe um jeito de julgar qualquer resposta candidata. Escolhido um conjunto de
números, dá para calcular qual era a chance de o histórico real ter saído
exatamente daquele jeito. Um conjunto ruim torna o que aconteceu muito
improvável; um conjunto bom torna o que aconteceu provável.

**Máxima verossimilhança** é o nome de procurar o conjunto que torna o histórico
observado o mais provável possível. Isso não é um menu de opções onde eu escolho
a que me agrada mais: é uma conta de otimização, com **uma resposta só** para
cada base e cada janela de tempo. Rodando de novo amanhã, com os mesmos dados,
sai o mesmo número.

### Por que "ir testando até o erro ficar bom" seria pior

É tentador ir mexendo nos parâmetros até a métrica de erro ficar bonita. O
problema é que isso responde à pergunta errada: em vez de *"que números
descrevem melhor esses clientes?"*, você passa a responder *"que números fazem
este teste específico parecer bom?"*.

Aí o modelo aprende o teste, não o negócio — e o erro que você mostra na
apresentação some quando chega dado novo. No jargão isso se chama **vazamento**
(*leakage*), e é o erro mais comum e mais discreto da área.

O que de fato derrubou o erro aqui não foi mexer em parâmetro: foi acertar o
**regime de previsão** — prever um mês por vez, com o mês anterior já fechado,
em vez de projetar treze meses de uma vez. Isso levou o erro de 18% para 3,7%,
com os mesmos parâmetros.

---

### O que o computador calcula e o que eu decidi

| | |
|---|---|
| **r, α** — BG/NBD, ritmo de compra | **Calculado.** Descrevem a distribuição de onde sai o ritmo de cada cliente: r/α é a taxa média de compra da base, e o r sozinho diz o quanto os clientes diferem entre si. |
| **a, b** — BG/NBD, abandono | **Calculado.** Descrevem a chance de o cliente sumir depois de cada compra. a/(a+b) é essa chance na média da base. |
| **p, q, v** — Gamma-Gamma | **Calculado.** Mesma lógica, conta própria, usando só quem tem recompra — quem comprou uma vez só não tem ticket de recompra para informar nada. |
| Janela de calibração | **Minha decisão.** No mínimo 15 meses. Com 12, o parâmetro *b* estourava para ~97, o que equivale a dizer que ninguém nunca abandona, e o M12 vinha inflado. Decidido por estabilidade, não por erro. |
| Unidade de tempo | **Minha decisão.** Mês de 30,4375 dias. Não muda o ajuste — só deixa os números legíveis em meses em vez de dias. |
| Quem entra na base | **Minha decisão.** A safra 2009-12 ficou de fora, por censura à esquerda. Decidido pelo diagnóstico da própria safra (frequência 9,4 contra 3,9 das outras), não por tentativa e erro. |
| Elasticidade do ticket | **Calculada**, mas deixada como **controle no simulador** — é a premissa mais frágil do conjunto (R² de {r2}) e quem usa merece poder mexer nela em vez de engolir o número. Existe só porque esta versão acrescentou a alavanca de ticket no simulador; não fazia parte da entrega original. |

O ponto da tabela: as minhas decisões existem, são poucas, e cada uma tem um
motivo que não é "o erro ficou menor assim". Onde o erro entrou na decisão, ele
teve que valer em **todos** os cortes do backtest, não no melhor deles.

---

### Como a conta roda por dentro

Esta parte é para quem quiser conferir a implementação; pode pular sem perder o
fio.

Cada cliente entra na conta como três números: **x** (quantas compras repetidas
fez), **t_x** (quanto tempo passou entre a primeira e a última compra) e **T**
(há quanto tempo ele é cliente). O otimizador procura os quatro parâmetros que
maximizam a soma dessas contribuições.

**Os parâmetros são otimizados em logaritmo.** Os quatro precisam ser positivos.
Otimizar o log de cada um garante isso sem precisar travar o otimizador na
fronteira, que é onde ele costuma empacar.

**Três chutes iniciais, dois otimizadores.** Nelder-Mead primeiro, que não
precisa de derivada e atravessa região plana; L-BFGS-B depois, para refinar. Os
três chutes servem para detectar ótimo local — se cada um parasse num lugar, o
resultado não seria confiável. Os três param no mesmo ponto.

**As somas são feitas em log.** O termo que separa "cliente vivo" de "cliente
que abandonou" soma duas exponenciais que estouram a precisão do computador.
Somar via *log-sum-exp* evita isso. É o tipo de detalhe que não muda a
matemática e quebra a implementação.

---

### Como eu conferi que está certo

São três perguntas diferentes, e cada teste responde a uma.

**1. A implementação está certa?** Simulo 4 mil clientes artificiais a partir do
próprio processo do BG/NBD, com os parâmetros que eu mesma defini, ajusto o
modelo em cima dessa simulação e confiro se os números voltam. E confiro se a
fórmula fechada bate com a média de 20 mil clientes simulados — a diferença fica
abaixo de 1,5% em 3, 6 e 12 meses. É o teste que pega erro de sinal e de
constante, justamente o tipo de erro que um MAPE bonito esconde.

**2. O modelo acerta neste negócio?** Para cada safra, o modelo é reajustado
**sem nenhum cliente dela** — o ajuste nunca vê a safra que vai prever. Depois
cada mês é previsto com o que veio antes: com M0, M1 e M2 fechados, prevê-se o
M3; quando o M3 fecha, prevê-se o M4. Um mês por vez, que é como a curva de uma
safra é acompanhada na vida real.

| | Erro |
|---|---|
| Erro médio (MAPE) | **3,7%** |
| Erro em M12 | 1,8% |
| Viés médio | −0,1% |

São 186 previsões em 21 safras. Cada safra entra até onde já fechou — para
pontuar o M3 basta ter o M3 fechado, não os 13 meses —, então a matriz tem 21
safras em M1 e vai afinando até 10 em M12. O erro cai conforme a safra
amadurece: 5,2% em M1, 2,7% em M6, 1,8% em M12. Quanto mais histórico o cliente
acumulou, mais o modelo tem em que se apoiar.

**O simulador de safra nova é o caso oposto e merece o número dele.** Ali a
safra não existe, não há nenhum mês fechado, e a projeção vai até M12 de uma vez
só. No mesmo backtest isso dá **18,2%** de erro médio e **23,3%** em M12. É bem
maior, é o esperado de uma projeção sem nada em que se apoiar, e está escrito no
app para o simulador ser usado sabendo disso.

**3. Por que validar por safra e não por data?** O caminho mais óbvio seria
fixar uma data, ajustar até ali e projetar o futuro. Só que o modelo precisa de
pelo menos 15 meses de calibração e a base tem 24 — então a primeira data
possível é fev/2011, quando as safras que já fecharam os 13 meses **já tinham
fechado**. Os primeiros meses de vida delas nunca seriam futuro em corte nenhum,
e metade da matriz ficaria vazia. Deixar a safra de fora do ajuste resolve isso
sem inventar dado, e ainda permite avaliar cada safra até onde ela chegou.

A ressalva honesta: o ajuste usa dados de calendário posteriores ao período da
safra, vindos de outras safras. Um choque que atingisse a base inteira estaria
parcialmente "conhecido". O que não acontece — e é o que importa — é o modelo
ver a própria safra que está prevendo.

---
