### The problem

Finance needs to know how much a vintage of customers will be worth before the
vintage happens. When the acquisition team asks for budget to bring in 500 new
customers, the question that decides the investment isn't "how much did they
spend on the first purchase" — it's **how much they'll have spent in 12
months**.

An actuals dashboard answers that a year late. Here actual and forecast live on
the same chart: older vintages show what happened, recent ones show what the
model expects, and a vintage that doesn't even exist yet can be simulated.

---

### Why BG/NBD + Gamma-Gamma

The business is **non-contractual**: the customer doesn't cancel a
subscription, they just disappear. There's no churn event to label, so you
can't train a classifier — there's no target. The BTYD family solves this by
modeling the process that generates the purchases instead of the label that
doesn't exist:

**BG/NBD** treats each customer as two latent variables. While active, they
buy at their own rate λ ~ Gamma(r, α). After each purchase, they flip a coin
and drop out with probability p ~ Beta(a, b). We never observe λ or p — only
frequency, recency and age. The model inverts that and returns, for each
customer, how many purchases to expect in the next t months and the
probability that they're still alive.

**Gamma-Gamma** takes care of value. The individual ticket varies around the
customer's own average, and that average varies across customers. The
practical result is a weighted average: someone with a lot of history is
forecast by their own ticket; someone with little is pulled toward the base's
average. The required assumption is independence between frequency and ticket
— checked, not presumed: the correlation shows up in the sidebar and stays
around 0.05.

Future revenue = expected purchases × expected ticket.

---

### How each LTV axis becomes a curve

The model doesn't spit out one number per vintage. It produces a **curve by
month of life** for each of the three axes, and M3, M6 and M12 are just three
readings of that curve.

For each customer and each month k, the model answers two separate questions:

**How many purchases?** BG/NBD returns E[Y(t) | x, t_x, T] — the expected
purchases over the next t months, given what that customer has already done.
Summing over the vintage and dividing by the number of customers gives the
**cumulative frequency** curve.

**At what ticket?** Gamma-Gamma returns E[M | x, m̄] — the customer's expected
ticket, which is a weighted average between the ticket they've already
practiced and the base's ticket. In other words: **the average ticket is
forecast from the observed average ticket itself**, with the weight of the
individual history growing as the customer buys more. Someone with a single
purchase is forecast almost entirely by the base; someone with fifteen is
forecast almost entirely by themselves.

**Revenue** is the product: expected purchases × expected ticket, cumulated
month by month. Because the curve is cumulative, it never goes down.

The ticket curve can go down, and it does — it's the only one of the three
that isn't cumulative. The ticket at M12 isn't M0's plus a piece: it's an
average that moves as new purchases with different values come in. That's why
it shows up as level layers on the chart, not as stacked increment bars.

The cutoff splits the curve into two stretches. Up to the cutoff, each point is
a direct count in the base. After it, each point is the actual up to there
**plus** what the model projects for the missing piece — never the whole
forecast laid over the observed. That's why a vintage can have a solid M3 and
a hatched M12 on the same bar.

---

### How the new-vintage simulation works

A vintage that hasn't happened yet has no history: x = 0, t_x = 0, T = 0.
There's nothing to condition on. So the forecast swaps the conditional form for
BG/NBD's **unconditional** one:

- cumulative purchases at M_k = 1 (the acquisition itself) + E[X(k+1)], which
  depends only on time and the parameters r, α, a, b;
- the 1st-purchase ticket is what you pick on the slider — it's the only
  business lever;
- the repeat ticket comes from history, corrected by the elasticity:
  `repeat_ticket = base × (M0_ticket / average_M0_ticket) ^ 0.44`.

> **This piece is an addition in this version, not part of the original
> delivery.** There, the simulator projected the new vintage from the model's
> parameters, and that was it: there was no ticket control, and so no question
> of how the entry ticket carries over into repeat purchases. Here I wanted the
> lever — and a ticket lever that only moved M0 would leave the 13-month curve
> practically still, which would be worse than having no lever at all. So the
> question showed up together with the control, and the choice was between
> guessing that pass-through and measuring it. I chose to measure it.

That 0.44 exponent is the point that deserves attention. It wasn't guessed:
it's a log-log regression at the customer level between the 1st-purchase
ticket and the average repeat ticket. Raising the entry ticket does **not**
raise the repeat in the same proportion — someone who comes in paying double
repeats at a level 1.36× higher, not 2×. It's regression to the mean, the same
phenomenon Gamma-Gamma implements in the individual forecast.

Since that regression's R² is 0.25, the elasticity is exposed as a control in
the app instead of hidden in a constant. It's the weakest assumption of the
set, and whoever uses the simulator deserves to be able to test it.

<!-- GRAFICO_ELASTICIDADE -->

The simulated curve appears against the range of vintages that have already
closed all 13 months. If the scenario leaves the range, it's asking for
something the base never delivered — which doesn't make it impossible, but
means you have to explain where the difference would come from.

The simulated vintage can go into the first tab's charts, next to the real
ones — it's the **Include the simulated vintage in the charts** checkbox in
the sidebar. It shows up as one more bar, fully hatched, because it's 100%
forecast. Seeing the scenario drawn next to the vintages that actually
happened is the quickest sanity check there is: if the simulated bar stands out
from all the real ones, the scenario is asking for something the base never
delivered.


---

### What was built

**Models written from scratch** (`modelo/btyd.py`), in numpy + scipy. The
`lifetimes` library, the usual route, has been unmaintained since 2020 and
breaks with recent versions of pandas and scipy — a fragile dependency in an
app that needs to stay up. Here the likelihood, the closed-form formulas with
the Gauss hypergeometric function and the maximum-likelihood fit are explicit
and tested.

**Validation is by parameter recovery**: `tests/test_btyd.py` simulates
customers from the generating process with known parameters, fits the model and
checks that the numbers come back. It also checks that the closed form of
E[X(t)] matches the average of 20 thousand simulated customers (error < 1.5%).
It's the test that catches sign and constant errors — things a nice-looking
MAPE hides.

**The vintage reading is by customer anniversary**, not by calendar month:
M_k is the window of the first (k+1) months of that customer's life. That way
someone who joined on the 30th doesn't get a one-day M0.

---

### The three decisions that changed the result

**1. The 2009-12 vintage was discarded.** The base starts on Dec 1, 2009, so
anyone who was already a customer before that shows up as if they'd been
acquired that month. That's 951 customers — three times the average of the
other vintages — with an M12 frequency of 9.4 against 3.9 for the rest.
They're not new customers, they're old customers with truncated history.
Leaving them in inflated the new-vintage forecast by 12% and pushed the
frequency × ticket correlation from 0.05 to 0.10, at the limit of what
Gamma-Gamma tolerates. Left-censoring is the kind of thing that doesn't show up
in the MAPE: the model misses just the same, only systematically upward.

**2. Short calibration windows were discarded.** With 12 months of history,
BG/NBD can't identify the dropout process: parameter b blew up to ~97, which
amounts to saying nobody ever churns, and the M12 projection came out
inflated. From 15 months on the fit stabilizes. That's why the cutoff-date
slider starts in Feb 2011 and not earlier.

**3. The ticket elasticity was estimated at the customer level, not the
vintage.** (This item only exists because this version added the ticket
control to the simulator — see the simulation section.) At the vintage level
you're left with ~23 noisy averages and the coefficient swung between -0.03
and 0.69 depending on the cutoff. At the customer level, with thousands of
points, it stays stable at 0.44 across every cutoff. It's the assumption that
links the simulator's slider to the forecast, so it had to be stable.

---

### How to read the charts

One rule applies to everything: **solid color and solid line = already
happened; hatching and dotted line = the model talking.** The cutoff date in
the sidebar is the simulation's "today" — dragging it back makes whole
vintages leave the actual and enter the forecast.

In the stacked bars, each group is a vintage and each bar is a cumulative
milestone: M0, then M0 + what came up to M3, up to M6, up to M12. The color
identifies the piece of the lifecycle and is the same in every vintage, so you
can compare bands across the chart.

The quality tab doesn't use the cutoff date: it refits the model without each
vintage's customers and forecasts one month at a time, with the previous one
already closed — with M0–M2 it forecasts M3, with M0–M3 it forecasts M4. The
average error is **3.7%**, with a −0.1% bias, and it falls as the vintage
matures: 5.2% at M1, 2.7% at M6, 1.8% at M12. Each vintage counts as far as it
has closed, so there are 21 vintages at M1 and 10 at M12.

---

### What runs in real time, and what doesn't

Fitting BG/NBD is expensive: about 3 seconds of optimization per cutoff date,
and there are 10 cutoffs. Running that on every click would make the app
unusable. But fitting is also **deterministic** — given the base and the
window, the result is always the same. There's no reason to redo it.

So the architecture separates the two things by cost, not by laziness:

**Offline, once (`prep/`).** For each cutoff, the model is fitted by maximum
likelihood and projected customer by customer, month by month. The result is
a 540-thousand-row panel — customer × month × cutoff — with actual and
forecast in separate columns. It's 1.5 MB compressed, versioned alongside the
code.

**Live, on every click.** Everything the app does on top of that panel is a
sum: filter by customer type and region, aggregate by vintage, turn it into a
stacked bar. That's instant for any combination of filters, because the heavy
work has already happened. Changing the cutoff date doesn't refit anything — it
changes which panel is being read.

**Truly live: the new vintage.** Here the model really runs, on every slider
move. The forecast for a customer with no history is
E[X(t)] = (a+b−1)/(a−1) · [1 − (α/(α+t))^r · ₂F₁(r, b; a+b−1; t/(α+t))], a
closed form that depends only on t and the four saved parameters. Evaluating
the Gauss hypergeometric function at 13 points takes microseconds — the
expensive part was finding r, α, a, b, not using them.

It's the same separation the Shiny app did in the original version: fitting is
batch, simulation is interactive. The difference is that here the boundary
between the two is written down, instead of hidden behind a "recalculate"
button.

In the static preview of this page the separation goes one step further: the
panel is exported as an aggregated cube and the closed form is reimplemented
in JavaScript, so the simulator works with no Python server behind it. What
can't be done there is refit the model — and that's exactly why the cutoffs
are fixed.

---

### Limits, stated upfront

- **The model knows nothing about campaigns, price or seasonality.** It
  extrapolates the observed purchase pattern. A vintage that comes in during
  an aggressive promotion will break the forecast, and that's a limitation of
  the method, not a bug.
- **The new-vintage simulator misses by 18% on average and 23% at M12.** It's
  a different problem, harder than forecasting one month at a time: there's no
  history at all to lean on. The number is in the quality tab precisely so the
  simulator is used knowing that.
- **The elasticity has an R² of 0.25.** The entry ticket explains only part of
  the repeat purchase. That's why the slider stays exposed: you can test the
  assumption instead of swallowing the number.
- **The base is UK online retail, 2009-2011**, in pounds displayed as R$.
  What transfers is the method, not the levels.

---

### Data and stack

[Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
(UCI): 1.07 million rows, Dec 1, 2009 to Dec 9, 2011. After cleaning — no
cancellations, no negative values, no codes that aren't products, only
identified customers — 36 thousand transactions and 5.8 thousand customers
remain, of whom 4.9 thousand enter the model. **72% have a repeat purchase**,
which is what makes the base suitable for BTYD (Olist, the more obvious choice
for being Brazilian, has ~3% and the model would have nothing to estimate).

Python · numpy · scipy · pandas · Plotly · Streamlit. No `lifetimes`.

**Code:** [github.com/GabiGattiRodrigues/cassandra](https://github.com/GabiGattiRodrigues/cassandra)
