# The preflight inequality (extension, Part A)

This is the cost model preregistered in `docs/PREREGISTRATION.md` (replay and cost model), solved for the change rate at which a check starts paying for itself. Validation results are in `results/extension/RESULTS_EXT.md`. The formulas were designed after the full study's results were seen, and frozen before any extension number was computed (tag `prereg-ext-v1`).

## Setting

An agent takes a screenshot, plans one action, which takes planning time $C$, and acts after a gap. A **check** may run just before acting. It takes time $\delta$ and either lets the action go or asks for a new plan.

| Symbol | Meaning |
|---|---|
| $p$ | chance the planned target changes during the gap (the click would miss) |
| $C$ | planning time per plan (s) |
| $\delta$ | check time (s); $\tau = \delta / C$ |
| $r$ | recall: share of changed steps the check flags |
| $f$ | false-alarm rate: share of unchanged steps the check flags |
| $k$ | cost of a stale action, in planning rounds (the wasted action, noticing it, and re-planning) |
| $\Delta t$ | the gap (s) |

## A.1 First-order form

Without a check, a changed step costs a stale action and an unchanged step costs nothing extra:

$$E_0 = p\,k\,C.$$

With a check, every step pays $\delta$. A caught change costs one re-plan, a missed change still costs $kC$, and a false alarm costs one re-plan:

$$E_1 = \delta + p\,[\,r\,C + (1-r)\,k\,C\,] + (1-p)\,f\,C.$$

The check pays when $E_1 < E_0$. Divide by $C$ and collect the terms in $p$:

$$\tau + p\,r + p\,(1-r)\,k + (1-p)\,f < p\,k \iff \tau + f < p\,[\,r\,(k-1) + f\,],$$

which gives the **break-even change rate**

$$\boxed{\,p^{*} = \frac{\tau + f}{r\,(k-1) + f}\,}, \qquad \text{the check pays when } p > p^{*}.$$

In words: the check's own time (relative to a plan) plus its false alarms must be repaid by the plans it saves, which are $k - 1$ per caught change.

**Assumptions** (each one is a place the model can be wrong):

1. A caught stale action costs exactly one re-plan.
2. A missed stale action costs $k$ plans.
3. A false alarm costs one re-plan.
4. The check runs on every step.
5. Re-plans do not go stale themselves.
6. The check's own duration opens no new exposure: a change during the check is not counted.

**Rearranged as budgets.** For a given $p$, $k$ and $C$, the largest false-alarm rate and the longest check time that still pay are:

$$f_{\max} = \frac{p\,r\,(k-1) - \tau}{1-p}, \qquad \delta_{\max} = C\,[\,p\,r\,(k-1) - (1-p)\,f\,].$$

## A.2 Second-order form

This form relaxes assumption 6 and adds re-aims at the preregistered costs.

**Exposure during the check.** If the change time is uniform over the gap, a check that looks $\delta$ before the action misses changes in the last $\delta$, so its effective recall is

$$r_{\text{eff}} = r\,\Bigl(1 - \frac{\delta}{\Delta t}\Bigr).$$

**Re-aims.** Some flags are resolved by re-aiming at the target's new place instead of re-planning. On a changed step, write the outcome shares (from dev) as follows. The three flagged shares are each scaled by $(1 - \delta/\Delta t)$, with the lost share added to $s_{\text{go}}$.

- $s_{\text{go}}$: not flagged
- $s_{\text{rp}}$: re-planned
- $s_{\text{ok}}$: re-aimed onto the target
- $s_{\text{wr}}$: re-aimed onto something else

On an unchanged step, write $f_{\text{rp}}$ for false re-plans and $f_{\text{wr}}$ for re-aims that miss. Costs in units of $C$: stale $k$, re-plan 1, wrong re-aim 3, successful re-aim 0 beyond $\delta$. Then

$$m_1 = s'_{\text{go}}\,k + s'_{\text{rp}} + 3\,s'_{\text{wr}}, \qquad \varphi = f_{\text{rp}} + 3\,f_{\text{wr}},$$

$$\boxed{\,p^{*}_{(2)} = \frac{\tau + \varphi}{k - m_1 + \varphi}\,}.$$

With no re-aims and $\delta/\Delta t \to 0$, $m_1 = (1-r)k + r$ and $\varphi = f$, which gives back A.1.

## An exploratory exposure term (not preregistered)

The preregistered replay scores each action against the page **at the moment of the action**, at least $\delta$ after the check's frames. In the replay, a change that lands during the check does not show up as lower recall. It shows up on the *unchanged* branch: the page was valid when the check looked, the check said go, and by action time the click misses. Let $h$ be the dev share of unchanged steps that go stale this way. Charging those at $kC$ gives

$$p^{*}_{(h)} = \frac{\tau + f + h\,k}{r\,(k-1) + f + h\,k}.$$

This form was written after the preregistered forms were computed, and it is reported as exploratory.

## The checker rubric (Part B)

For one question asked at one step, the expected cost of checker $X$ is

$$E_X = \delta_X + q\,(1 - r_X)\,M + (1 - q)\,f_X\,C.$$

Here $q$ is how often the problem occurs at that step, and $M$ is the extra cost of a miss over a catch, in seconds. A costlier checker $B$ beats a cheaper checker $A$ when

$$q\,M\,(r_B - r_A) > (\delta_B - \delta_A) + (1 - q)\,(f_B - f_A)\,C,$$

so escalate from $A$ to $B$ when the miss cost exceeds

$$\boxed{\,M^{*} = \frac{(\delta_B - \delta_A) + (1-q)\,(f_B - f_A)\,C}{q\,(r_B - r_A)}\,}.$$

If $r_B \le r_A$, never escalate. If $M^{*} \le 0$, $B$ is better on every count, so always use it.
