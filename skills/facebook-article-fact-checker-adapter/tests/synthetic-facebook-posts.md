# Synthetic Test Cases for facebook-article-fact-checker-adapter

Seven synthetic Facebook post scenarios covering the required test cases.

---

## Test 1 — Facebook post accurately summarizes a mostly accurate article

**Purpose:** Verify that the adapter does not manufacture framing issues when the post is a fair representation of a reliable article.

**Input:**
```json
{
  "facebook_post_text": "Interesting read — CDC data shows overdose deaths declined slightly in 2023 for the first time in years, though still at a very high level. The fentanyl crisis continues to be the main driver. Article linked.",
  "article_url": "https://synthetic-test.invalid/cdc-overdose-2023",
  "depth": "standard"
}
```

**Synthetic article (hypothetical for testing):**
```
Title: U.S. Overdose Deaths Fell Slightly in 2023, CDC Reports
Author: Health Correspondent
Publication: Associated Press
Date: 2024-03-15

Drug overdose deaths in the United States declined slightly in 2023 to approximately
107,000, down from a record 111,000 in 2022, according to provisional data from the
Centers for Disease Control and Prevention. Health officials cautioned that the
improvement, while welcome, does not represent a turning point in the opioid crisis.

Fentanyl remained the dominant driver of overdose deaths, accounting for roughly
73 percent of fatalities. The slight decline tracks with increased distribution of
naloxone and expanded access to medication-assisted treatment in some states.

"This is not a victory lap," said Dr. Rahul Gupta, director of the White House
Office of National Drug Control Policy. "We have more work to do."
```

**Expected findings:**

Facebook framing analysis:
- `post_accurately_represents_article`: `true`
- No framing issues detected
- Post is accurate summary: slight decline, still high, fentanyl main driver

Article fact-check (delegated):
- Key claims mostly supported by CDC data
- Dr. Gupta quote should be verified against primary source
- Factual accuracy: 4–5
- Rhetorical transparency: 4–5 (article is measured; post is measured)

Combined assessment:
- "The Facebook post accurately summarizes the article. Both the post and the article represent the CDC data fairly. No misleading framing found."

---

## Test 2 — Facebook post exaggerates a cautious article

**Purpose:** Verify the adapter detects overstatement in the post framing when the article itself is measured and includes appropriate caveats.

**Input:**
```json
{
  "facebook_post_text": "SCIENTISTS CONFIRM: Daily coffee PREVENTS Alzheimer's disease!! Share this with every coffee lover you know! Finally proof that what we enjoy is also protecting our brains!",
  "article_url": "https://synthetic-test.invalid/coffee-cognition-study",
  "depth": "standard"
}
```

**Synthetic article (hypothetical for testing):**
```
Title: New Study Finds Association Between Coffee Consumption and Lower Dementia Rates
Author: Science Correspondent
Publication: ScienceDaily
Date: 2024-05-10

A study from Uppsala University tracking 1,412 adults over 18 years found that those
who consumed three or more cups of coffee per day had a 22 percent lower incidence of
dementia compared to low consumers. The association was statistically significant.

However, the study's authors emphasized that the findings are observational and cannot
establish a causal relationship. Lead researcher Dr. Anna Lindqvist stated: "Our data
show a clear relationship between coffee consumption and reduced rates of dementia —
though we emphasize this is an observational finding and further RCT research is needed
before clinical recommendations can be made."

The paper calls for randomized controlled trials before any clinical guidance is issued.
No recommendation to increase coffee intake was made.
```

**Expected findings:**

Facebook framing analysis:
- `post_accurately_represents_article`: `false`
- Issues:
  - `certainty_inflation` (high): "SCIENTISTS CONFIRM" — article says observational, not confirmed
  - `certainty_inflation` (high): "PREVENTS Alzheimer's" — article says "association," not prevention
  - `claim_addition` (high): "Finally proof" — article explicitly disclaims proof
  - `urgency_pressure` (low): "Share this with every coffee lover" — mild urgency without suppression
- Post strips the study's central caveat (observational, not causal)

Article fact-check (delegated):
- The article itself is mostly accurate
- The cautious framing of the original study is preserved in the article
- Factual accuracy: 4–5
- Rhetorical transparency: 4–5

Combined assessment:
- "The article accurately reports an observational study that found an association between coffee and lower dementia rates. The Facebook post significantly overstates the findings, replacing 'association' with 'prevents' and 'proof,' and omitting the study's explicit caution against causal interpretation. The article is reliable; the post misrepresents it."

---

## Test 3 — Misleading headline where article body is more nuanced

**Purpose:** Verify the adapter catches framing issues introduced by the Facebook preview headline when the article body tells a different story.

**Input:**
```json
{
  "facebook_post_text": "Wow. Just wow.",
  "article_url": "https://synthetic-test.invalid/senator-endorses-ending-program",
  "depth": "standard"
}
```

**Synthetic article (hypothetical for testing):**
```
Title: Senator Mitchell Declares She Wants to 'End This Program'
Author: Capitol Correspondent
Publication: PolicyWatch
Date: 2024-07-02

Senator Patricia Mitchell (R-TX) made waves Tuesday when she stated during a Senate
hearing that "we should end this program," referring to the State Department's $15
billion foreign assistance allocation.

However, in context, Senator Mitchell's full statement made clear she was calling for
oversight reform, not elimination. Her complete remark: "Some of my colleagues are
saying we should end this program, but I disagree — we should end this program's lack
of oversight, not the program itself. I support continued funding with independent
auditing."

Mitchell has long pushed for accountability measures in foreign aid spending. Her
office confirmed that her position supports the program with reforms, not its
elimination.
```

**Expected findings:**

Facebook framing analysis:
- `post_accurately_represents_article`: partial — the post ("Wow. Just wow.") implies outrage without explaining context; the article body contradicts its own headline
- Issues:
  - `context_stripping` (high): Facebook preview likely shows the misleading headline; the post text adds no correction
  - `loaded_presupposition` (medium): "Wow. Just wow." implies the headline claim is shocking/outrageous without prompting the reader to read further

Article fact-check (delegated):
- Q001: Senator's quote — `truncated_misleadingly` in headline but accurate in article body
- Article headline is itself misleading; body corrects it
- Context completeness: 2–3 (headline misleads, body clarifies, but headline dominates social sharing)

Combined assessment:
- "The article headline is misleading — it implies the Senator supports ending the program when her full statement shows she supports the opposite. The article body corrects this, but Facebook previews typically show only the headline and description. The poster's 'Wow. Just wow.' adds emotional framing without prompting readers to check the full story."

---

## Test 4 — Facebook caption adds a false claim not present in the article

**Purpose:** Verify the adapter detects when the poster introduces an entirely new false claim not found in the linked article.

**Input:**
```json
{
  "facebook_post_text": "The government is now officially requiring all children to be vaccinated against their parents' wishes — no religious exemptions allowed. Article here. This is TYRANNY. Share before they remove it.",
  "article_url": "https://synthetic-test.invalid/state-vaccine-policy-update",
  "depth": "standard"
}
```

**Synthetic article (hypothetical for testing):**
```
Title: State Updates School Immunization Requirements, Religious Exemptions Remain
Author: Education Reporter
Publication: State Tribune
Date: 2024-08-20

The state health department has updated its school immunization schedule to add a
booster requirement for students entering sixth grade. The policy aligns the state
with CDC recommendations adopted by 38 other states.

Religious and medical exemptions remain available under the updated policy. Parents
seeking an exemption must submit a signed form to their school district. The policy
affects new sixth-grade enrollment beginning next fall.

Health officials noted the update follows a regional measles cluster this spring.
No penalties beyond enrollment holds are imposed; exempt students may attend school
with documentation on file.
```

**Expected findings:**

Facebook framing analysis:
- `post_accurately_represents_article`: `false`
- Issues:
  - `claim_addition` (high): "no religious exemptions allowed" — article explicitly states exemptions remain
  - `certainty_inflation` (high): "officially requiring all children" — policy applies to sixth-grade enrollment only
  - `claim_addition` (high): "against their parents' wishes" — article describes an opt-out exemption process
  - `urgency_pressure` (high): "Share before they remove it" — conspiracy sealing + urgency
  - `conspiracy_sealing` (medium): Implies censorship without evidence
  - `evidence_substitution` (medium): Post presents false claims as stated in article, which they are not

Article fact-check (delegated):
- Article's claims are mostly verifiable and measured
- Factual accuracy: 4–5
- Rhetorical transparency: 4–5

Combined assessment:
- "The Facebook caption contains multiple false claims that are directly contradicted by the article it links to. The article explicitly states religious exemptions remain, the policy applies only to sixth-grade enrollment, and parents can opt out with documentation. The post adds these false claims independently of the article. Do not share without verifying the article directly."

---

## Test 5 — Screenshot-only post with insufficient article access

**Purpose:** Verify the adapter handles the case where only a screenshot is available and the article URL cannot be determined or retrieved.

**Input:**
```json
{
  "screenshot_paths": ["C:/tests/synthetic/fb-post-no-url.png"],
  "depth": "quick"
}
```

**Synthetic screenshot content (described for testing):**
The screenshot shows a Facebook post with text: "This new report says 5G towers are causing a spike in childhood cancer rates in every city where they've been installed. The mainstream media is silent." No article URL is visible in the screenshot. The shared article preview shows a headline: "5G and Cancer: What They're Not Telling You" with a description "New data shows correlation..." but no URL is visible.

**Expected behavior:**

Step 1 (Intake):
- Access mode: C (screenshot-based extraction)
- Extraction confidence: low (no URL visible)

Step 2 (Facebook extraction):
- Partial extraction: post text recovered, headline and description visible
- Shared article URL: not found

Adapter should stop and request:
> "I extracted the following from the screenshot:
> - Post text: 'This new report says 5G towers are causing a spike in childhood cancer rates...'
> - Visible headline: '5G and Cancer: What They're Not Telling You'
> - Visible description: 'New data shows correlation...'
>
> I could not find a shared article URL in the screenshot. Please either:
> 1. Paste the article URL directly
> 2. Paste the article text
> 3. Provide a clearer screenshot that includes the article link"

**Expected output limitations:**
- No article fact-check possible without article content
- Partial framing notes may be recorded from visible text
- Combined assessment notes the limitation explicitly

---

## Test 6 — Post using urgency and conspiracy-sealing language

**Purpose:** Verify the adapter detects multiple suppression patterns in the post even when the article itself has mixed accuracy.

**Input:**
```json
{
  "facebook_post_text": "SHARE THIS BEFORE IT GETS DELETED. The truth about the water supply that the government is hiding. They've been poisoning us for years and now there's proof. Anyone who tells you this isn't happening is either paid off or brainwashed. The mainstream media won't cover this — THAT'S HOW YOU KNOW IT'S TRUE.",
  "article_url": "https://synthetic-test.invalid/water-fluoride-study",
  "depth": "standard"
}
```

**Synthetic article (hypothetical for testing):**
```
Title: Study Questions Fluoride Levels in Some Municipal Water Systems
Author: Environmental Reporter
Publication: Environmental Health News
Date: 2024-04-12

A peer-reviewed study published in Environmental Health Perspectives examined fluoride
concentrations in 400 municipal water systems and found that 12 systems — primarily
in rural areas — had fluoride levels exceeding EPA secondary guidelines, not primary
safety standards.

The study authors noted that exceeding secondary guidelines does not constitute a
health hazard but may affect water aesthetics such as taste. No link to cancer or
neurological harm was found at these levels. The EPA primary health standard was not
exceeded in any system studied.

"This is a compliance and monitoring question, not a safety crisis," said the lead
author. "We are not suggesting municipal water is unsafe."
```

**Expected findings:**

Facebook framing analysis:
- `post_accurately_represents_article`: `false`
- Issues:
  - `urgency_pressure` (high): "SHARE THIS BEFORE IT GETS DELETED"
  - `conspiracy_sealing` (high): "THAT'S HOW YOU KNOW IT'S TRUE" — absence of coverage used as proof of cover-up
  - `epistemic_bullying` (high): "paid off or brainwashed" — disagreement framed as corruption
  - `certainty_inflation` (high): "They've been poisoning us for years" — article finds no health hazard
  - `claim_addition` (high): "poisoning us" — article explicitly says no safety standards were exceeded
  - `context_stripping` (high): Post omits that the study found no health hazard and that the lead author explicitly denied a safety crisis

Article fact-check (delegated):
- Article's claims are well-supported and measured
- Factual accuracy: 4–5
- Rhetorical transparency: 4–5

Combined assessment:
- "The article reports a real but limited study finding: some rural water systems exceed cosmetic (secondary) fluoride guidelines, with no health hazard. The Facebook post completely inverts this, claiming government poisoning and cover-up. The post uses six distinct critical-thinking suppression patterns. The article is reliable; the post is not a fair representation of it."

---

## Test 7 — Post using emotional language that is not manipulative

**Purpose:** Verify the adapter does NOT flag emotional language as a framing violation when the post accurately represents a serious article and the emotion is proportionate to the subject.

**Input:**
```json
{
  "facebook_post_text": "107,000 people died of overdoses last year. 107,000. Read this. These are our neighbors, our families. The numbers are real and we need to talk about this.",
  "article_url": "https://synthetic-test.invalid/overdose-2023-cdc",
  "depth": "standard"
}
```

**Synthetic article (hypothetical for testing):**
```
Title: The Preventable Tragedy: How America's Overdose Crisis Took 107,000 Lives Last Year
Author: Maya Chen
Publication: The Reckoning
Date: 2024-02-20

One hundred and seven thousand Americans died of drug overdoses in 2023. The CDC's
final 2023 mortality data confirms the toll. Fentanyl accounted for approximately
73 percent of all overdose deaths. The 107,000 figure represents a slight decline
from the record 111,000 deaths recorded in 2022.

"We are watching the largest drug crisis in American history unfold in slow motion,
and the policy response has not matched the scale of the emergency," said Dr. Sarah
Wakeman, addiction medicine specialist at Massachusetts General Hospital.
```

**Expected findings:**

Facebook framing analysis:
- `post_accurately_represents_article`: `true`
- No framing issues
- Post is emotionally resonant but factually accurate and does not add false claims, urgency pressure, or suppression patterns
- "These are our neighbors, our families" is not manipulative — it contextualizes a real statistic
- No urgency language, no conspiracy framing, no claim addition

Article fact-check (delegated):
- Key statistics match CDC data
- Emotional tone in both post and article is not penalized
- Rhetorical transparency score: 4–5

Combined assessment:
- "The Facebook post accurately represents the article and adds only proportionate emotional context to a verified statistic. No misleading framing detected in either the post or the article. Both are good-faith representations of CDC overdose data."
