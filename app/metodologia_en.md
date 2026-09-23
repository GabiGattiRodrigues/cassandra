### The question this tab answers

> *"How did you choose the model's parameters?"*

The short answer is: **I didn't.** The parameters are calculated by the
computer, and it has no freedom to arrive at a different result. What I chose
was something else — and it's all separated and listed further down.

If you're not from the field, the next two blocks are worth reading. They
explain, without formulas, what that sentence means.

---

### What "estimating" a parameter means

Imagine you have the purchase history of {n_clientes} customers and want to
summarize that group in a few numbers — basically two: **how often these
people tend to buy** and **how easily they tend to disappear**.

There's a way to judge any candidate answer. Given a set of numbers, you can
calculate how likely it was for the real history to have come out exactly the
way it did. A bad set makes what happened very unlikely; a good set makes what
happened likely.

**Maximum likelihood** is the name for looking for the set that makes the
observed history as likely as possible. It's not a menu of options where I pick
the one I like best: it's an optimization, with **a single answer** for each
dataset and each time window. Run it again tomorrow, with the same data, and
you get the same number.

### Why "trying until the error looks good" would be worse

It's tempting to keep tweaking the parameters until the error metric looks
nice. The problem is that this answers the wrong question: instead of *"which
numbers best describe these customers?"*, you start answering *"which numbers
make this particular test look good?"*.

Then the model learns the test, not the business — and the error you show in
the presentation disappears when new data arrives. In the jargon this is called
**leakage**, and it's the most common and most discreet mistake in the field.

What actually brought the error down here wasn't touching parameters: it was
getting the **forecasting regime** right — forecasting one month at a time,
with the previous month already closed, instead of projecting thirteen months
in one go. That took the error from 18% to 3.7%, with the same parameters.

---

### What the computer calculates and what I decided

| | |
|---|---|
| **r, α** — BG/NBD, purchase rhythm | **Calculated.** They describe the distribution each customer's purchase rhythm comes from: r/α is the base's average purchase rate, and r alone says how much customers differ from each other. |
| **a, b** — BG/NBD, dropout | **Calculated.** They describe the chance a customer disappears after each purchase. a/(a+b) is that chance on average across the base. |
| **p, q, v** — Gamma-Gamma | **Calculated.** Same logic, its own math, using only customers with repeat purchases — someone who bought only once has no repeat ticket to inform anything. |
| Calibration window | **My decision.** At least 15 months. With 12, parameter *b* blew up to ~97, which amounts to saying nobody ever drops out, and M12 came out inflated. Decided for stability, not for error. |
| Time unit | **My decision.** A 30.4375-day month. It doesn't change the fit — it just makes the numbers readable in months instead of days. |
| Who enters the base | **My decision.** The 2009-12 vintage was left out, because of left-censoring. Decided from the vintage's own diagnosis (frequency 9.4 against 3.9 for the others), not by trial and error. |
| Ticket elasticity | **Calculated**, but left as a **control in the simulator** — it's the weakest assumption of the set (R² of {r2}) and whoever uses it deserves to be able to move it instead of swallowing the number. It only exists because this version added the ticket lever to the simulator; it wasn't part of the original delivery. |

The point of the table: my decisions exist, they're few, and each one has a
reason that isn't "the error got smaller this way". Where error played a part
in a decision, it had to hold across **every** backtest cutoff, not just the
best one.

---

### How the math runs inside

This part is for anyone who wants to check the implementation; you can skip it
without losing the thread.

Each customer enters the math as three numbers: **x** (how many repeat
purchases they made), **t_x** (how much time passed between the first and last
purchase) and **T** (how long they've been a customer). The optimizer looks for
the four parameters that maximize the sum of those contributions.

**The parameters are optimized in log.** All four have to be positive.
Optimizing the log of each one guarantees that without having to pin the
optimizer to the boundary, which is where it usually gets stuck.

**Three starting points, two optimizers.** Nelder-Mead first, which needs no
derivative and crosses flat regions; L-BFGS-B next, to refine. The three
starting points are there to detect local optima — if each one stopped in a
different place, the result wouldn't be reliable. All three stop at the same
point.

**Sums are done in log.** The term that separates "alive customer" from
"customer who dropped out" adds two exponentials that blow the computer's
precision. Summing via *log-sum-exp* avoids that. It's the kind of detail that
doesn't change the math and breaks the implementation.

---

### How I checked it's right

There are three different questions, and each test answers one.

**1. Is the implementation right?** I simulate 4 thousand artificial customers
from the BG/NBD process itself, with parameters I set myself, fit the model on
that simulation and check that the numbers come back. And I check that the
closed-form formula matches the average of 20 thousand simulated customers —
the difference stays below 1.5% at 3, 6 and 12 months. It's the test that
catches sign and constant errors, exactly the kind of error a nice-looking MAPE
hides.

**2. Does the model get it right in this business?** For each vintage, the
model is refitted **without any of its customers** — the fit never sees the
vintage it's going to forecast. Then each month is forecast with what came
before: with M0, M1 and M2 closed, M3 is forecast; when M3 closes, M4 is
forecast. One month at a time, which is how a vintage curve is tracked in real
life.

| | Error |
|---|---|
| Average error (MAPE) | **3.7%** |
| Error at M12 | 1.8% |
| Average bias | −0.1% |

That's 186 forecasts across 21 vintages. Each vintage counts as far as it has
closed — to score M3 it only needs M3 closed, not all 13 months —, so the
matrix has 21 vintages at M1 and thins out to 10 at M12. The error falls as the
vintage matures: 5.2% at M1, 2.7% at M6, 1.8% at M12. The more history the
customer has built up, the more the model has to lean on.

**The new-vintage simulator is the opposite case and deserves its own
number.** There the vintage doesn't exist, there's no closed month, and the
projection goes to M12 in one go. In the same backtest that gives **18.2%**
average error and **23.3%** at M12. It's much larger, it's what you'd expect
from a projection with nothing to lean on, and it's written in the app so the
simulator is used knowing that.

**3. Why validate by vintage and not by date?** The most obvious path would be
to fix a date, fit up to it and project the future. But the model needs at
least 15 months of calibration and the base has 24 — so the first possible
date is Feb 2011, when the vintages that had closed all 13 months **had
already closed**. Their first months of life would never be the future at any
cutoff, and half the matrix would be empty. Leaving the vintage out of the fit
solves this without inventing data, and still lets each vintage be evaluated
as far as it got.

The honest caveat: the fit uses calendar data after the vintage's period,
coming from other vintages. A shock hitting the whole base would be partly
"known". What doesn't happen — and that's what matters — is the model seeing
the very vintage it's forecasting.

---
