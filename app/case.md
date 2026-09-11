### O problema

Finanças precisa saber quanto uma safra de clientes vai valer antes de a safra
acontecer. Quando o time de aquisição pede orçamento para trazer 500 clientes
novos, a pergunta que decide o investimento não é "quanto eles gastaram na
primeira compra" — é **quanto eles vão ter gastado em 12 meses**.

Um dashboard de realizado responde isso com um ano de atraso. Aqui o realizado
e a previsão convivem no mesmo gráfico: as safras antigas mostram o que
aconteceu, as recentes mostram o que o modelo espera, e a safra que ainda nem
existe pode ser simulada.

---

### Por que BG/NBD + Gamma-Gamma

O negócio é **não-contratual**: o cliente não cancela assinatura, ele só some.
Não existe evento de churn para rotular, então não dá para treinar um
classificador — não há alvo. A família BTYD resolve isso modelando o processo
que gera as compras em vez do rótulo que não existe:

**BG/NBD** trata cada cliente como duas variáveis latentes. Enquanto está ativo,
compra a uma taxa própria λ ~ Gamma(r, α). Depois de cada compra, joga uma moeda
e abandona com probabilidade p ~ Beta(a, b). Nunca observamos λ nem p — só
frequência, recência e idade. O modelo inverte isso e devolve, para cada
cliente, quantas compras esperar nos próximos t meses e a probabilidade de ele
ainda estar vivo.

**Gamma-Gamma** cuida do valor. O ticket individual varia em torno de uma média
própria do cliente, e essa média varia entre clientes. O resultado prático é
uma média ponderada: quem tem muito histórico é previsto pelo próprio ticket;
quem tem pouco é puxado para a média da base. A hipótese exigida é
independência entre frequência e ticket — checada, não presumida: a correlação
aparece na barra lateral e fica em torno de 0,05.

Receita futura = compras esperadas × ticket esperado.

---

### Como cada eixo do LTV vira uma curva

O modelo não cospe um número por safra. Ele produz uma **curva por mês de vida**
para cada um dos três eixos, e é dessa curva que M3, M6 e M12 são apenas três
leituras.

Para cada cliente e cada mês k, o modelo responde duas perguntas separadas:

**Quantas compras?** O BG/NBD devolve E[Y(t) | x, t_x, T] — as compras esperadas
nos próximos t meses, dado o que aquele cliente já fez. Somando sobre a safra e
dividindo pelo número de clientes sai a curva de **frequência acumulada**.

**A que ticket?** O Gamma-Gamma devolve E[M | x, m̄] — o ticket esperado do
cliente, que é uma média ponderada entre o ticket que ele mesmo já praticou e o
ticket da base. Ou seja: **o ticket médio é previsto a partir do próprio ticket
médio observado**, com o peso do histórico individual crescendo conforme o
cliente compra mais. Quem tem uma compra só é previsto quase inteiramente pela
base; quem tem quinze é previsto quase inteiramente por si.

**Receita** é o produto: compras esperadas × ticket esperado, acumulado mês a
mês. Como a curva é acumulada, ela nunca desce.

A do ticket pode descer, e desce mesmo — é a única das três que não é
acumulável. O ticket em M12 não é o de M0 mais um pedaço: é uma média que se
move conforme entram compras novas com valores diferentes. Por isso ele aparece
em camadas de nível no gráfico, e não em barras empilhadas de incremento.

O corte separa a curva em dois trechos. Até o corte, cada ponto é contagem
direta na base. Depois dele, cada ponto é o realizado até ali **mais** o que o
modelo projeta para o pedaço que falta — nunca a previsão inteira jogada por
cima do observado. É por isso que uma safra pode ter o M3 cheio e o M12
hachurado na mesma barra.

---

### Como a simulação de safra nova funciona

Uma safra que ainda não aconteceu não tem histórico: x = 0, t_x = 0, T = 0. Não
há em que condicionar. Então a previsão troca a forma condicional pela
**incondicional** do BG/NBD:

- compras acumuladas em M_k = 1 (a própria aquisição) + E[X(k+1)], que depende
  só do tempo e dos parâmetros r, α, a, b;
- o ticket da 1ª compra é o que você escolhe no slider — é a única alavanca de
  negócio;
- o ticket das recompras sai do histórico, corrigido pela elasticidade:
  `ticket_recompra = base × (ticket_M0 / ticket_M0_médio) ^ 0,44`.

> **Este pedaço é acréscimo desta versão, não da entrega original.** Lá o
> simulador projetava a safra nova a partir dos parâmetros do modelo, e pronto:
> não havia controle de ticket, e portanto não havia a pergunta de como o ticket
> de entrada se propaga para as recompras. Aqui eu quis a alavanca — e uma
> alavanca de ticket que mexesse só no M0 deixaria a curva de 13 meses
> praticamente parada, o que seria pior do que não ter alavanca nenhuma. Então a
> pergunta apareceu junto com o controle, e a escolha era entre chutar esse
> repasse e medi-lo. Preferi medir.

Esse expoente 0,44 é o ponto que merece atenção. Ele não foi chutado: é uma
regressão log-log no nível do cliente entre o ticket da 1ª compra e o ticket
médio das recompras. Subir o ticket de entrada **não** sobe a recompra na mesma
proporção — quem entra pagando o dobro recompra num patamar 1,36× maior, não 2×.
É regressão à média, o mesmo fenômeno que o Gamma-Gamma implementa na previsão
individual.

Como o R² dessa regressão é 0,25, a elasticidade fica exposta como controle no
app em vez de escondida numa constante. É a premissa mais frágil do conjunto, e
quem usa o simulador merece poder testá-la.

<!-- GRAFICO_ELASTICIDADE -->

A curva simulada aparece contra a faixa das safras que já fecharam os 13 meses.
Se o cenário sai da faixa, ele está pedindo algo que a base nunca entregou — o
que não o torna impossível, mas obriga a explicar de onde viria a diferença.

A safra simulada pode entrar nos gráficos da primeira aba, ao lado das reais —
é a marcação **Incluir a safra simulada nos gráficos** na barra lateral. Ela
aparece como mais uma barra, inteiramente hachurada, porque é 100% previsão. Ver
o cenário desenhado ao lado das safras que de fato aconteceram é o teste de
sanidade mais rápido que existe: se a barra simulada destoa de todas as reais, o
cenário está pedindo algo que a base nunca entregou.


---

### O que foi construído

**Modelos escritos do zero** (`modelo/btyd.py`), em numpy + scipy. A biblioteca
`lifetimes`, que é o caminho usual, está sem manutenção desde 2020 e quebra com
versões recentes de pandas e scipy — dependência frágil em um app que precisa
ficar de pé. Aqui a verossimilhança, as fórmulas fechadas com a hipergeométrica
gaussiana e o ajuste por máxima verossimilhança estão explícitos e testados.

**A validação é por recuperação de parâmetros**: `tests/test_btyd.py` simula
clientes a partir do processo gerador com parâmetros conhecidos, ajusta o
modelo e confere se os números voltam. Também confere se a fórmula fechada de
E[X(t)] bate com a média de 20 mil clientes simulados (erro < 1,5%). É o teste
que pega erro de sinal e de constante — coisas que um MAPE bonito esconde.

**A leitura de safra é por aniversário do cliente**, não por mês de calendário:
M_k é a janela dos primeiros (k+1) meses de vida daquele cliente. Assim quem
entrou dia 30 não ganha um M0 de um dia.

---

### As três decisões que mudaram o resultado

**1. A safra 2009-12 foi descartada.** A base começa em 01/12/2009, então quem
já era cliente antes disso aparece como se tivesse sido adquirido naquele mês.
São 951 clientes — três vezes a média das outras safras — com frequência em M12
de 9,4 contra 3,9 das demais. Não são clientes novos, são clientes antigos com
histórico truncado. Deixá-los dentro inflava a previsão de safra nova em 12% e
levava a correlação frequência × ticket de 0,05 para 0,10, no limite do que o
Gamma-Gamma tolera. Censura à esquerda é o tipo de coisa que não aparece no
MAPE: o modelo erra igual, só que sistematicamente para cima.

**2. Janelas de calibração curtas foram descartadas.** Com 12 meses de
histórico, o BG/NBD não identifica o processo de abandono: o parâmetro b
estourava para ~97, o que equivale a dizer que ninguém nunca churna, e a
projeção de M12 vinha inflada. A partir de 15 meses o ajuste estabiliza. Por
isso o slider de data de corte começa em fev/2011 e não antes.

**3. A elasticidade do ticket foi estimada no cliente, não na safra.** (Este
item existe só porque esta versão acrescentou o controle de ticket no
simulador — ver a seção da simulação.) No nível
da safra sobram ~23 médias ruidosas e o coeficiente oscilava entre -0,03 e
0,69 conforme o corte. No nível do cliente, com milhares de pontos, ele fica
estável em 0,44 em todos os cortes. É a premissa que liga o slider do
simulador à previsão, então precisava ser estável.

---

### Como ler os gráficos

Uma regra vale para tudo: **cor cheia e linha sólida = já aconteceu; hachura e
linha pontilhada = o modelo falando.** A data de corte na barra lateral é o
"hoje" da simulação — arrastá-la para trás faz safras inteiras saírem do
realizado e entrarem na previsão.

Nas barras empilhadas, cada grupo é uma safra e cada barra é um marco
acumulado: M0, depois M0 + o que veio até M3, até M6, até M12. A cor identifica
o pedaço do ciclo de vida e é a mesma em todas as safras, então dá para comparar
faixas na horizontal.

A aba de qualidade não usa a data de corte: ela reajusta o modelo sem os
clientes de cada safra e prevê um mês por vez, com o anterior já fechado — com
M0–M2 prevê o M3, com M0–M3 prevê o M4. O erro médio é de **3,7%**, com viés de −0,1%,
e cai conforme a safra amadurece: 5,2% em M1, 2,7% em M6, 1,8% em M12. Cada
safra entra até onde já fechou, então são 21 safras em M1 e 10 em M12.

---

### O que roda em tempo real, e o que não roda

Ajustar o BG/NBD é caro: são ~3 segundos de otimização por data de corte, e
existem 10 cortes. Rodar isso a cada clique deixaria o app inutilizável. Mas
ajustar também é **determinístico** — dada a base e a janela, o resultado é
sempre o mesmo. Não há motivo para refazer.

Então a arquitetura separa as duas coisas por custo, não por preguiça:

**Offline, uma vez (`prep/`).** Para cada corte, o modelo é ajustado por máxima
verossimilhança e projetado cliente a cliente, mês a mês. O resultado é um
painel de 540 mil linhas — cliente × mês × corte — com o realizado e o previsto
separados em colunas próprias. São 1,5 MB comprimidos, versionados junto com o
código.

**Ao vivo, a cada clique.** Tudo que o app faz em cima desse painel é soma:
filtrar por tipo de cliente e região, agregar por safra, virar em barra
empilhada. Isso é instantâneo para qualquer combinação de filtros, porque o
trabalho pesado já aconteceu. Trocar a data de corte não reajusta nada — troca
qual painel está sendo lido.

**Ao vivo de verdade: a safra nova.** Aqui o modelo roda mesmo, a cada
movimento do slider. A previsão de um cliente sem histórico é
E[X(t)] = (a+b−1)/(a−1) · [1 − (α/(α+t))^r · ₂F₁(r, b; a+b−1; t/(α+t))], uma
forma fechada que depende só de t e dos quatro parâmetros salvos. Avaliar a
hipergeométrica gaussiana em 13 pontos custa microssegundos — o caro era achar
r, α, a, b, não usá-los.

É a mesma separação que o Shiny fazia na versão original: o ajuste é batch, a
simulação é interativa. A diferença é que aqui a fronteira entre as duas está
escrita, em vez de escondida atrás de um botão de "recalcular".

Na prévia estática dessa página a separação vai um passo além: o painel é
exportado como um cubo agregado e a forma fechada é reimplementada em
JavaScript, então o simulador funciona sem nenhum servidor Python atrás. O que
não dá para fazer lá é reajustar o modelo — e é exatamente por isso que os
cortes são fixos.

---

### Limites, ditos na cara

- **O modelo não sabe de campanha, preço nem sazonalidade.** Ele extrapola o
  padrão de compra observado. Uma safra que entrar em uma promoção agressiva
  vai furar a previsão, e isso é uma limitação do método, não um bug.
- **O simulador de safra nova erra 18% em média e 23% em M12.** É outro
  problema, mais difícil que prever um mês por vez: não há nenhum histórico em
  que se apoiar. O número está na aba de qualidade justamente para o simulador
  ser usado sabendo disso.
- **A elasticidade tem R² de 0,25.** O ticket de entrada explica só parte da
  recompra. Por isso o slider fica exposto: dá para testar a premissa em vez de
  engolir o número.
- **A base é de varejo online do Reino Unido, 2009-2011**, em libras exibidas
  como R$. O que se transfere é o método, não os patamares.

---

### Base e stack

[Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
(UCI): 1,07 milhão de linhas, 01/12/2009 a 09/12/2011. Depois da limpeza —
sem cancelamento, sem valor negativo, sem código que não é produto, só cliente
identificado — sobram 36 mil transações e 5,8 mil clientes, dos quais 4,9 mil
entram no modelo. **72% têm recompra**, que é o que torna a base adequada ao
BTYD (a Olist, mais óbvia por ser brasileira, tem ~3% e o modelo não teria o
que estimar).

Python · numpy · scipy · pandas · Plotly · Streamlit. Sem `lifetimes`.

**Código:** [github.com/GabiGattiRodrigues/cassandra](https://github.com/GabiGattiRodrigues/cassandra)
