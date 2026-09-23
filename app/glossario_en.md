Every term below appears somewhere in the app. The idea is that you can read
the whole project without knowing the CLV literature beforehand — so
everything here is written in plain language, and the technical name comes
along only so you recognize it when it shows up elsewhere.

**If you read only one paragraph, read this one.** The app takes the customers
who made their first purchase in the same month, calls that group a
**vintage**, and tracks how much that group bought month by month since the
first purchase. Where the base already has the data, the number is a count: it
happened. Where it doesn't yet, a model comes in that estimates what will
probably happen. The app makes clear, all the time, which of the two you're
looking at.

---

### The vintage reading

**Vintage (or *cohort*).** The group of customers who made their first
purchase in the same month. Vintage 2010-03 is everyone whose initial purchase
fell in March 2010. Once in the vintage, always in the vintage — the customer
doesn't change group later.

*Why group this way:* customers from different months are at different points
in their lives. Comparing a two-year customer with a two-month one says
nothing; comparing two customers at the same month of life says a lot.

**M0, M1, … M12.** The customer's months of life, counted from **their first
purchase**, not from the calendar. M0 is the first month of life, M3 is the
first 4 months, M12 is 13 months.

*Why not use the calendar month:* someone who joined on the 30th would have a
one-day M0, and the comparison between vintages would be skewed. Here the M0
of someone who joined on the 30th runs until the 29th of the next month.

**Cumulative.** Every M_k number counts from the first purchase, not just what
happened in that month. Revenue at M6 already includes M0 to M5. That's why the
revenue curve never goes down.

**Actual × forecast.** *Actual* is a direct count in the base: it happened,
it's recorded. *Forecast* is what the model expects for the piece that hasn't
happened yet. In the app, **solid color = actual, hatching = forecast** — and
a single bar can have both, when the cutoff date falls in the middle of that
piece.

**Cutoff date.** The simulation's "today". Everything up to it is actual; from
there on it's the model. Dragging the cutoff back makes whole vintages leave
the actual and enter the forecast — it's the way to watch the model being
tested against a past you already know.

---

### The three metrics

**Purchase frequency.** How many purchases the customer made, on average,
cumulative up to that month.

`frequency = vintage's total purchases ÷ number of customers`

A vintage with frequency 3.9 at M12 bought, on average, 3.9 times in the first
13 months of life.

**Average ticket.** How much a purchase is worth, on average.

`ticket = total revenue ÷ number of purchases`

It's the only one of the three that **isn't cumulative**: M12's ticket isn't
M0's plus a piece, it's an average that moves as new purchases come in — and
it can fall.

**Revenue per customer.** The product of the two: `frequency × ticket`, or,
equivalently, `total revenue ÷ number of customers`. It's the metric that
answers "how much is a customer from this vintage worth", and it's the one the
finance team uses to decide how much it's worth paying to acquire a new
customer.

**LTV / CLV (customer lifetime value).** It's revenue per customer seen as a
project: how much that customer will generate in total. Here it's truncated at
13 months, because that's the horizon the base allows you to **check**.
"Infinite" LTV exists in theory, but it's a number nobody can verify.

---

### The model, in plain words

**Non-contractual business.** The customer doesn't cancel anything: they just
stop buying, and you never find out. There's no churn date to record.

That has a big practical consequence: **you can't train a churn model**,
because there's no "this customer left" label for the model to learn. The way
out is different — instead of predicting a label that doesn't exist, model the
behavior that generates the purchases. That's what the **BTYD** family (*Buy
Till You Die*) is for.

**BG/NBD** — answers **how many purchases** to expect. The idea is simple to
tell: each customer has their own purchase rhythm and their own stubbornness to
keep going or disappear. Neither is directly observable. The model assumes
these two traits vary across people following a known distribution, looks at
everyone's history together and figures out the shape of those distributions.
With that in hand, it can say how many purchases to expect from each customer
from here on.

- **r and α** describe the purchase rhythm. **r/α** is the base's average rate
  — here ≈ 0.25, or one purchase every 4 months. **r** alone says how much
  customers differ from each other: a low r means a very heterogeneous base.
- **a and b** describe dropout. **a/(a+b)** is the average chance a customer
  disappears after each purchase — here ≈ 5%.

**Gamma-Gamma** — answers **at what value** those purchases happen. It assumes
each customer's ticket varies around their own average, and that this average
varies across customers. In practice the result is a sensible weighted
average: someone with a lot of history is forecast by their own ticket;
someone with little is pulled toward the base's average, because with two
purchases you can't trust that value is really theirs.

**x, t_x and T.** The three numbers that summarize each customer for BG/NBD.

- **x** = how many repeat purchases they made (the first doesn't count, it's
  the acquisition);
- **t_x** = how much time passed between the first and the last purchase;
- **T** = how long they've been a customer, up to the cutoff date.

A customer with a high x and t_x close to T is buying until now. A customer
with a high x and a low t_x bought a lot and vanished.

**P(alive).** The probability that the customer is still active, given what
they did. It's not observable — it's what the model infers. Someone who had a
rhythm and stopped a long time ago has a low P(alive).

**Conditional × unconditional forecast.** *Conditional* is the forecast for a
customer **who already has history**: it uses their x, t_x and T.
*Unconditional* is the forecast for a customer who doesn't exist yet — there's
nothing to lean on, so the forecast comes only from the model's parameters and
time. The new-vintage simulator is this second case, and that's why its error
is larger.

**Likelihood and maximum likelihood.** Likelihood is the chance that the model,
with a given set of parameters, generated exactly the history you observed.
Maximizing the likelihood is looking for the parameters that make what happened
as likely as possible. **It's not a menu of values to test** — it's an
optimization with a single answer, given the base and the window.

---

### The assumptions and the diagnostics

**Ticket elasticity.** It answers a practical question: *if the vintage comes
in with a higher first-purchase ticket, how much of that carries over into the
repeat purchases?*

It exists here because of a choice in this version of the project: the
simulator has an entry-ticket lever, and something needs to link that lever to
the repeat ticket. In the original Petlove delivery there was no such control,
so this question wasn't asked.

The answer isn't a multiplier, it's an exponent:

`repeat_ticket = average_repeat_ticket × (M0_ticket ÷ average_M0_ticket) ^ elasticity`

- elasticity **1** = proportional pass-through. Double the entry, double the
  repeat.
- elasticity **0** = the entry ticket says nothing about the repeat.
- elasticity **0.44** (the value estimated here) = double the entry, the
  repeat rises 2^0.44 = **1.36×**, not 2×.

It's estimated by a regression at the customer level: the 1st-purchase ticket
on the x axis, the average repeat ticket on the y axis, both in log. On a log
scale the slope of the line already *is* the elasticity — that's the reason
for using log, not an aesthetic choice.

**Regression to the mean.** It's the phenomenon behind that elasticity below 1.
Someone who had an exceptionally high first purchase was, in part, lucky — and
luck doesn't repeat. On the next purchase the person tends to come back close
to the average. It's the same mechanism Gamma-Gamma applies when it pulls a
customer with little history toward the base's average.

**Frequency × ticket correlation.** Gamma-Gamma only holds if those who buy
more don't systematically have a different ticket from those who buy less. The
usual criterion is |correlation| < 0.1. Here it's around 0.05 — the assumption
passes, and the number is in the sidebar precisely so it can be checked rather
than presumed.

**Left-censoring.** It happens when the base starts after the business. Those
who were already customers show up as if they'd been acquired in the base's
first month — not a new customer, an old customer with their history cut off.
Here that hit the 2009-12 vintage, which had a frequency of 9.4 at M12 against
3.9 for the others. That's why it was removed.

---

### How the error is measured

**MAPE (mean absolute percentage error).** The average percentage error,
without sign: `|forecast − actual| ÷ actual`, averaged. A MAPE of 4% means the
forecast misses by 4% up or down, on average. It doesn't say which way.

**Bias.** The same error, but **with** sign: `(forecast − actual) ÷ actual`.
Positive bias means the model systematically over-forecasts.

*Why the two appear together:* a 5% MAPE with +5% bias is much worse than a 5%
MAPE with 0% bias. The first always misses the same way, and an error that
always goes the same way piles up in the budget.

**Out-of-sample.** Measuring error on the same data used to fit the model
measures nothing — the model has already seen the answer. Out-of-sample error
is measured on data the fit never saw.

**Leakage.** When information from the test leaks into training by accident.
The most common and most discreet form: choosing the model specification by
looking at the result of the same test you'll later report. The number comes
out nice and is worthless.

**Cross-validation by vintage (*leave-one-cohort-out*).** That's how the error
is measured here. To evaluate vintage 2010-03, the model is refitted **without
any of its customers** — the fit never sees the vintage it's going to
forecast. Then it projects that vintage's life and compares it with what
actually happened. And this repeats vintage by vintage.

**One-step-ahead forecast.** The regime used in the quality tab: each month is
forecast with the previous month already closed. With M0, M1 and M2 in hand,
M3 is forecast; when M3 closes, M4 is forecast. It's how a vintage curve is
tracked in practice, and it's the reason the error stays at 3.7% — well below
the 18% of projecting 13 months in one go, with no history.
