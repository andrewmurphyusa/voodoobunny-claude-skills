# Synthetic Test Articles for article-fact-checker

Four synthetic articles covering the four required test scenarios:
1. A cited academic paper being misrepresented
2. A quote being truncated misleadingly
3. Emotional but not manipulative language
4. Rhetoric that suppresses critical thinking

---

## Test Article 1 — Misrepresented Academic Paper

**Purpose:** Test that the skill detects overstatement and correlation/causation confusion when an article misrepresents a study's findings.

```
Title: Daily Coffee Habit Cuts Alzheimer's Risk in Half, New Study Confirms
Author: Staff Writer
Publication: WellnessToday
Date: 2024-03-15

A groundbreaking study from researchers at Uppsala University has confirmed that
drinking three or more cups of coffee per day cuts your risk of Alzheimer's disease
by 50 percent. The study, which followed 1,400 participants for 20 years, proves
that caffeine is a direct preventative against cognitive decline.

"Our data show a clear relationship between coffee consumption and reduced rates
of dementia," said lead researcher Dr. Anna Lindqvist.

Health experts are now calling for coffee to be incorporated into standard
preventative care for aging populations. "The evidence is overwhelming," said
one neurologist quoted in the report.

Alzheimer's currently affects 6.7 million Americans, and rates are projected to
nearly double by 2060 without intervention.
```

**What the actual Uppsala study says (hypothetical for testing):**
- 22% lower incidence of dementia in high-coffee consumers vs. low consumers
- The association was statistically significant but the paper explicitly states: "Our findings demonstrate correlation and cannot be used to infer causation"
- Dr. Lindqvist's actual quote: "Our data show a clear relationship between coffee consumption and reduced rates of dementia — though we emphasize this is an observational finding and further RCT research is needed before clinical recommendations can be made"
- Sample size: 1,412 over 18 years (not 20)
- The paper calls for more research; it does not recommend coffee as preventative care

**Expected findings:**
- C001 (50% risk reduction): `false` — paper reports 22%, not 50%
- C002 (proves direct prevention): `misleading` — paper explicitly disavows causal inference
- Q001 (Dr. Lindqvist quote): `truncated_misleadingly` — second half of quote omitted changes the claim's meaning
- N001 (1,400 participants / 20 years): `misleading` — actual figures are 1,412 and 18 years
- Underlying source: `does_not_support` — overstatement + confusing_correlation_with_causation

---

## Test Article 2 — Quote Truncated Misleadingly

**Purpose:** Test that the skill detects a quote that has been cut to reverse or substantially change the speaker's meaning.

```
Title: Senator Mitchell Endorses End to Foreign Aid Program
Author: Capitol Correspondent
Publication: PolicyWatch
Date: 2024-07-02

Senator Patricia Mitchell (R-TX) declared her support for ending the State
Department's foreign assistance program during Tuesday's Senate hearing.

"We should end this program," the Senator said, responding to questions about
the annual $15 billion allocation.

Mitchell has long been a critic of foreign spending and her statement signals
a potential shift in Republican caucus priorities ahead of the budget vote
scheduled for September.
```

**What the full transcript says (hypothetical for testing):**
Full quote: "Some of my colleagues are saying we should end this program, but I disagree — we should end this program's lack of oversight, not the program itself. I support continued funding with independent auditing."

**Expected findings:**
- Q001: `truncated_misleadingly` — the article quotes a fragment that, in context, is part of a statement opposing the position the article attributes to the senator
- C001 (Senator endorsed ending program): `false`
- Framing: context stripping detected

---

## Test Article 3 — Emotional Language, Factually Accurate

**Purpose:** Test that the skill does NOT penalize emotional language when the underlying facts are well-supported.

```
Title: The Preventable Tragedy: How America's Overdose Crisis Took 107,000 Lives Last Year
Author: Maya Chen
Publication: The Reckoning
Date: 2024-02-20

One hundred and seven thousand Americans died of drug overdoses in 2023. That is
not an abstraction. That is more than every American killed in the Vietnam War,
combined. Each of those deaths was somebody's child, parent, sibling, or friend.

The CDC's final 2023 mortality data, released this month, confirms the toll. Fentanyl
accounted for approximately 73 percent of all overdose deaths, a sharp increase from
the 15 percent it represented a decade ago.

Experts have described the current situation as a "fourth wave" of the opioid crisis,
driven by illicitly manufactured fentanyl and an increasingly adulterated drug supply.
The previous waves involved prescription opioids (starting around 1999), then heroin
(around 2010), and synthetic opioids first detected in significant numbers around 2013.

"We are watching the largest drug crisis in American history unfold in slow motion,
and the policy response has not matched the scale of the emergency," said Dr. Sarah
Wakeman, addiction medicine specialist at Massachusetts General Hospital.

The 107,000 figure represents a slight decline from the record 111,000 deaths recorded
in 2022 — a fact the CDC noted while cautioning that any optimism must be tempered by
the overall scale of the crisis.
```

**What the evidence actually shows (hypothetical for testing):**
- CDC provisional data for 2023 does show approximately 107,000 overdose deaths
- Fentanyl proportion ~73% is consistent with CDC data
- Vietnam War US deaths: approximately 58,000 — article says "more than every American killed in the Vietnam War, combined" which is accurate
- Four-wave framework is widely used in public health literature
- Dr. Wakeman is a real addiction medicine specialist at MGH; quote is attributed but should be verified
- 2022 figure of 111,000 is consistent with CDC data; article correctly contextualizes the decline

**Expected findings:**
- Facts check out across all major claims
- Emotional language ("preventable tragedy," "watching in slow motion") does NOT trigger framing violations
- No manipulative framing patterns detected
- Rhetorical transparency score: 4 or 5 (strong — emotional but evidence-backed)
- Factual accuracy score: 4 or 5

---

## Test Article 4 — Rhetoric Suppressing Critical Thinking

**Purpose:** Test that the skill detects multiple manipulative framing patterns even when some underlying facts may be real.

```
Title: They're Poisoning Your Children and the Media Won't Tell You
Author: WakeUpFreedomDesk
Publication: TruthPatriot.net
Date: 2024-09-01

THEY DON'T WANT YOU TO KNOW THIS. Share this article before it gets taken down.

Every honest parent already understands the truth: the government's school lunch
program is deliberately designed to make children sick and dependent. No rational
person could deny the connection between processed food and childhood health problems.
Anyone who tells you otherwise is either paid off or too blind to see it.

A "study" — if you can even call it that — supposedly found no link between school
lunches and long-term health outcomes. But think about who funded it. The food
industry owns these researchers. That's not conspiracy, that's just how the world
works. The silence from mainstream media proves they're in on it.

Wake up. You either care about your children's health or you're part of the problem.
There is no middle ground.

Thousands of parents across the country are pulling their kids from public schools
because of this. Real Americans know the truth. Share this now.

Sources: personal testimonials, "multiple experts" (names withheld for their protection)
```

**Expected findings:**
- Framing patterns detected:
  - `urgency_pressure` (high): "Share this before it gets taken down," "Share this now"
  - `conspiracy_sealing` (high): "The silence from mainstream media proves they're in on it" — treats contradictory evidence as confirmation
  - `epistemic_bullying` (high): "No rational person could deny," "Anyone who tells you otherwise is either paid off or too blind"
  - `false_binary` (high): "You either care about your children's health or you're part of the problem"
  - `evidence_substitution` (high): "personal testimonials," "multiple experts (names withheld)" — no verifiable sources
  - `outgroup_contamination` (medium): "Real Americans know the truth" — implies skeptics are not real Americans
  - `certainty_inflation` (high): "Every honest parent already understands the truth," "No rational person could deny"
- Factual claims: mostly unverifiable due to absent sources
- Rhetorical transparency score: 0 or 1
- Factual accuracy score: unable_to_verify for most claims (no citable sources)
- NOTE: the skill should NOT infer the author "intends to deceive" — it should note the effect of the language patterns on the reader's ability to evaluate claims
