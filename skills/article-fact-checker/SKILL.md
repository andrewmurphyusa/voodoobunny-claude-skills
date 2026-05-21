---
name: article-fact-checker
description: Evaluates the factual reliability of an article by checking historical and current facts, quote accuracy, numerical claims, cited source fidelity, and manipulative framing. Source-agnostic — accepts article text, a URL, or both. Returns a structured report with per-claim verdicts, evidence citations, and reliability scores. Use when a user pastes article text or a URL and wants to know what's true, what's misleading, and what needs more context.
---

<objective>
Systematically fact-check an article by extracting every meaningful factual claim, gathering evidence from tiered sources, verifying quotes against their originals, checking numerical figures against primary data, testing whether cited sources actually support what the article says they support, and detecting language designed to suppress critical thinking.

Return a structured report that tells the user which claims are well-supported, which are misleading or false, which need more context, and whether the article's rhetoric is designed to bypass careful reasoning.

This skill is source-agnostic. It works on any article regardless of topic, publication, or political angle. It does not classify articles by political side unless a factual claim is directly about a political matter.
</objective>

<quick_start>
**Usage:** Invoke with article content. Supply at minimum one of `article_url` or `article_text`.

```
/article-fact-checker                          # prompts for article input
/article-fact-checker depth=quick              # check top 5–10 claims only
/article-fact-checker depth=deep               # check all meaningful claims
/article-fact-checker output_format=json       # machine-readable output
/article-fact-checker user_focus="vaccine safety claims"   # prioritize a specific area
```

**Input fields (all optional except at least one of article_url / article_text):**

| Field | Type | Description |
|---|---|---|
| `article_url` | string | URL of the article |
| `article_text` | string | Full article body (preferred when both are given) |
| `article_title` | string | Article headline |
| `article_author` | string | Byline |
| `article_publication` | string | Publisher / outlet |
| `article_date` | string | Publication date |
| `article_metadata` | object | Any additional metadata |
| `user_focus` | string | Area the user wants prioritized |
| `depth` | enum | `quick` (top 5–10) · `standard` (top 10–20, default) · `deep` (all) |
| `output_format` | enum | `summary` · `detailed` (default) · `evidence_table` · `json` |

**If both `article_url` and `article_text` are provided**, use `article_text` as the primary body and use the URL for metadata and source discovery.

**If only `article_url` is provided**, attempt safe retrieval using `WebFetch`. If retrieval fails, report the failure clearly and ask the user to paste the article text.

**If neither is provided**, ask the user to supply the article.
</quick_start>

<context>
This skill uses sub-agents for underlying source checks. The sub-agent prompt is at:
`skills/article-fact-checker/underlying-source-checker.md`

Source tier definitions, evidence evaluation rubric, and manipulative framing rubric are embedded in the workflow steps below.

**What this skill does NOT do:**
- No social-media scraping, authentication, or feed access
- No Facebook integration
- No browser automation
- No political ideology scoring
- No censorship or suppression of minority arguments
- No defamatory certainty about individuals without strong evidence
- No assumption that mainstream, official, academic, or alternative sources are automatically correct
</context>

<workflow>

<step_1_intake>
**Article Intake — normalize all available information**

Extract or normalize:
- Title
- Author
- Publisher / publication
- Publication date
- Article URL
- Full article text
- Section headings
- All hyperlinks and citations (inline and footnotes)
- Embedded block quotes and inline quotes
- Named individuals (with role/context if stated)
- Named organizations (with context if stated)
- Claimed dates and time periods
- Claimed numbers, percentages, dollar amounts, counts, rankings
- Named studies, reports, academic papers, laws, datasets, datasets, prior news reports, government documents

**If article_text is missing and only article_url is provided:**
1. Attempt retrieval via `WebFetch`
2. Extract article body from the returned HTML/text
3. If retrieval fails (paywall, timeout, 4xx/5xx), report clearly:
   > "Could not retrieve article from [URL]: [reason]. Please paste the article text directly."
   Then stop and wait.

**If neither article_text nor article_url is provided:**
> "Please provide the article text or URL to fact-check."
Then stop and wait.

After intake, print a brief confirmation:
```
Article intake complete.
Title: [title or "unknown"]
Author: [author or "unknown"]
Publication: [publication or "unknown"]
Date: [date or "unknown"]
Quotes found: [N]
Named individuals: [list]
Named organizations: [list]
Numerical claims detected: [N]
Citations/links found: [N]
```
Proceed automatically without waiting for user confirmation.
</step_1_intake>

<step_2_claim_extraction>
**Claim Extraction — identify and classify factual claims**

Read the full article and extract every meaningful factual assertion. Assign each a unique ID (C001, C002, …).

**Claim types:**
- `historical` — event, date, or figure from the past
- `current_event` — recent or ongoing event
- `legal_regulatory` — law, regulation, court ruling, policy, enforcement
- `scientific_medical` — study finding, medical fact, scientific consensus
- `statistical_numerical` — number, percentage, dollar amount, count, rank, ratio
- `quote_attribution` — attributed spoken or written statement
- `causal` — X caused Y
- `comparative` — X is greater/less/faster/worse than Y
- `prediction_speculation` — X will happen, X is likely to happen
- `interpretation_opinion` — author's reading of events (not a factual assertion)
- `cited_source_claim` — the article says an underlying source says or shows something

**Separate and do NOT fact-check (unless they contain an embedded factual assertion):**
- Pure opinion without factual content
- Rhetorical questions
- Satire or parody (if labeled)
- Metaphor
- Moral judgment
- Policy preference without a factual claim embedded

**For each claim, record:**
```json
{
  "id": "C001",
  "claim_text": "exact or close-paraphrase of the claim as stated",
  "claim_type": "[type from list above]",
  "article_location": "paragraph N / section heading",
  "attributed_to": "author assertion | [person/org name] | cited source",
  "linked_source_url": "if the claim links to or cites a source, that URL or title"
}
```

Output the full claim list before proceeding. This list is the input to all later steps.
</step_2_claim_extraction>

<step_3_prioritization>
**Claim Prioritization — rank by importance and verifiability**

Score each claim on these factors (1 point each, higher = higher priority):
1. Central to the article's main argument
2. Potentially harmful if false
3. Specific and verifiable (not vague)
4. Cites an underlying source that can be checked
5. Repeated multiple times in the article
6. Contains a numerical or statistical figure
7. Rhetorical loading detected (claim appears designed to provoke rather than inform)

Sort claims by score descending.

**Depth thresholds:**
- `quick` → top 5–10 claims
- `standard` → top 10–20 claims (default)
- `deep` → all claims with score ≥ 1

If `user_focus` is specified, elevate claims matching that focus to the top of the queue regardless of score.

Print the prioritized list before proceeding. Proceed automatically.
</step_3_prioritization>

<step_4_evidence_gathering>
**Evidence Gathering — research each priority claim**

For each priority claim, gather evidence using appropriate sources.

**Source Quality Tiers:**

**Tier A — Primary Sources (highest trust)**
Use whenever available.
- Original academic papers (full text preferred)
- Official government datasets (census, CDC, BLS, Eurostat, etc.)
- Court filings, judicial opinions, statutes, regulations
- Company filings (SEC, annual reports)
- Official transcripts (Congressional Record, Hansard, press conference transcripts)
- Original interviews (timestamped, archived)
- Official statements and press releases
- Government reports (GAO, CBO, IPCC, WHO, etc.)
- Archived web pages (Wayback Machine)
- Raw data files

**Tier B — High-Quality Secondary Sources (use for context and corroboration)**
- Major newswires and established news organizations (AP, Reuters, BBC, NYT, WSJ, etc.)
- Established fact-checking organizations (PolitiFact, FactCheck.org, Snopes, Full Fact, etc.)
- Peer-reviewed review articles and meta-analyses
- Academic and institutional explainers
- Expert summaries from credentialed specialists
- Nonpartisan research organizations (PEW, Brookings, RAND, etc.)

**Tier C — Contextual / Lower-Confidence Sources (label clearly, never sole support for important claims)**
- Blogs and personal websites
- Opinion pieces
- Social-media posts
- Advocacy organizations (any side)
- Think-tank summaries (label ideology if known)
- Wikipedia (useful for finding primary sources, not as proof itself)
- Partisan news outlets (label)
- Unverified reposts or screenshots

**For each claim, record:**
```json
{
  "claim_id": "C001",
  "evidence_found": true,
  "sources": [
    {
      "tier": "A|B|C",
      "title": "",
      "url": "",
      "date": "",
      "key_quote_or_finding": "",
      "supports_claim": "yes | mostly | partially | no | contradicts | unclear"
    }
  ],
  "verdict": "supported | mostly_supported | needs_context | misleading | unsupported | false | unable_to_verify",
  "confidence": "high | medium | low",
  "notes": ""
}
```

When evidence is inconclusive, say so explicitly. Do not force a verdict.
When sources conflict, name both sources and describe the conflict instead of choosing a side without clear reason.
For current facts, verify that sources are fresh enough (check dates).
</step_4_evidence_gathering>

<step_5_quote_verification>
**Quote Verification — check every attributed statement**

For each attributed quote (exact or paraphrased) found during intake:

1. Identify the exact text as it appears in the article
2. Identify the speaker or organization
3. Search for the original source (transcript, video, statement, interview, court document, etc.)
4. Compare the quoted text against the original

**Classify each quote as one of:**
- `exact` — matches original word for word (minor punctuation differences acceptable)
- `accurate_paraphrase` — paraphrased but meaning preserved
- `truncated_misleadingly` — cut in a way that changes the meaning
- `missing_context` — real and accurate but requires surrounding context to interpret correctly
- `misattributed` — attributed to wrong person or organization
- `fabricated` — no source found after diligent search; evidence of invention
- `satire_parody` — originated in a satirical source
- `unverifiable` — cannot find original source

For quotes from intermediary sources (article B quotes person X via article A):
- Note the intermediary
- Attempt to find the original primary statement
- Flag reliance on intermediary if primary not found

**Record for each quote:**
```json
{
  "quote_id": "Q001",
  "quoted_text_in_article": "",
  "attributed_to": "",
  "verdict": "[from list above]",
  "original_source_url": "",
  "original_source_text": "",
  "discrepancy_description": "",
  "confidence": "high | medium | low"
}
```
</step_5_quote_verification>

<step_6_numerical_verification>
**Numerical and Statistical Verification**

For each numerical figure, percentage, date, dollar amount, count, ranking, ratio, or comparison:

1. Record the exact claim as stated in the article
2. Identify the likely original data source (named in article, inferred, or searched)
3. Check all of the following:
   - **Units**: are the units correctly stated and consistently applied?
   - **Denominator**: is the base population or denominator correctly described?
   - **Timeframe**: is the time period correctly stated and still current?
   - **Geography / scope**: does the statistic apply to the place/group the article says it does?
   - **Absolute vs. relative confusion**: is a relative change being described as absolute or vice versa?
   - **Cherry-picking endpoints**: does the time window or comparison group selection flatter the claim?
   - **Unlike quantities compared**: are two genuinely non-comparable figures being treated as equivalent?
   - **Margin of error / uncertainty**: does precision exceed what the data supports?
   - **Staleness**: is this the most current data available, or has it been superseded?
   - **Sample size**: is a finding from a small or non-representative sample being overgeneralized?

**Classify each:**
- `supported` — figure is accurate in context
- `mostly_supported` — minor imprecision but substantially correct
- `needs_context` — accurate figure but missing information needed to interpret it correctly
- `misleading` — technically accurate but framed to create a false impression
- `unsupported` — cannot find data that produces this figure
- `false` — figure is contradicted by the primary data source
- `unable_to_verify` — source not accessible or data not publicly available

**Record for each:**
```json
{
  "figure_id": "N001",
  "article_claim": "",
  "data_source_found": "",
  "verdict": "[from list above]",
  "issues_found": [],
  "correct_figure_if_known": "",
  "confidence": "high | medium | low"
}
```
</step_6_numerical_verification>

<step_7_underlying_source_checks>
**Underlying Source Verification — sub-agent tasks for each cited source**

For every source the article cites, links, quotes from, or paraphrases, create a sub-agent task using the `underlying-source-checker` prompt (see `underlying-source-checker.md` in this skill's directory).

**Identify cited sources from:**
- Inline hyperlinks in the article body
- Named studies, reports, or papers (even without a link)
- Named laws, regulations, or court cases
- Named datasets, government reports, or official statements
- Prior news articles referenced

**For each underlying source, the sub-agent answers:**
```json
{
  "source_title": "",
  "source_type": "academic_paper | news_report | government_report | legal_document | dataset | transcript | other",
  "source_url": "",
  "article_claim_about_source": "",
  "what_source_actually_says": "",
  "does_source_support_article_claim": "yes | mostly | partially | no | unclear",
  "missing_context": [],
  "misrepresentation_type": [
    "none",
    "overstatement",
    "cherry_picking",
    "quote_mining",
    "confusing_correlation_with_causation",
    "wrong_population",
    "wrong_timeframe",
    "wrong_scope",
    "unsupported_generalization",
    "contradicted_by_source"
  ],
  "key_evidence": [],
  "confidence": "high | medium | low"
}
```

**Important:**
- The sub-agent must compare the article's *specific claim* against the underlying source.
- It must NOT merely summarize the underlying source.
- It must directly answer: "Does this source support what the article says it supports?"

**For academic papers, also require the sub-agent to assess:**
- Authors' actual findings vs. what the article claims
- Study design (RCT, observational, meta-analysis, etc.)
- Sample size and representativeness
- Stated limitations
- Whether later research contradicts or qualifies the finding
- Whether the article overgeneralizes from the paper's scope

**For legal or policy claims, require the sub-agent to distinguish:**
- Proposed law vs. passed law
- Regulation vs. statute
- Court ruling vs. court guidance vs. settlement
- Enforcement practice vs. written policy
- Political claim about law vs. what the law actually says

Integrate all sub-agent findings into the final report under "Underlying Source Checks."
</step_7_underlying_source_checks>

<step_8_framing_analysis>
**Critical-Thinking Suppression / Manipulative Framing Analysis**

Read the full article and identify language or structural patterns designed to reduce the reader's ability to evaluate claims critically.

**Do NOT penalize:**
- Emotional language by itself
- Strong advocacy with clear evidence
- Passionate argument for a position
- Confident assertions backed by good sources

**Target only language that obscures reasoning, discourages verification, or substitutes social/identity pressure for evidence.**

**Patterns to detect:**

**Certainty Inflation**
Presenting contested claims as settled fact.
Examples: "Everyone knows," "It is undeniable," "No honest person could disagree," "The science is settled" applied to mixed evidence.

**Outgroup Contamination**
Claiming a claim is false solely because disliked people or groups believe it.
Examples: Framing skepticism of X as proof of stupidity, betrayal, or moral corruption.

**Epistemic Bullying**
Substituting social pressure for evidence.
Examples: "Only an idiot would question this," "Do your own research" as a deflection from providing evidence, "Wake up" framing without substantiation.

**Urgency Pressure**
Creating artificial time pressure to prevent reflection.
Examples: "Share before it's deleted," "They don't want you to know this," "This is being suppressed," "Act now before it's too late."

**Conspiracy Sealing**
Making a claim unfalsifiable.
Examples: Treating lack of evidence as proof of cover-up, treating contradictory evidence as planted or controlled.

**Motte-and-Bailey Framing**
Advancing a strong claim, retreating to a weaker defensible claim when challenged, then treating defense of the motte as defense of the bailey.

**Loaded Question / Presupposition**
Embedding an unproven claim inside a question or framing device.
Examples: "Why does X keep hiding the truth about Y?" (presupposes both that X is hiding something and that Y is a truth).

**Scapegoating / Dehumanization**
Blaming complex problems on a simplistic villain. Describing groups of people as vermin, infestation, disease, contamination, or existential threat.

**False Binary**
Presenting two options when more exist.
Examples: "You are either with us or against us," "Either you support X or you hate [group]."

**Evidence Substitution**
Replacing evidence with vibes, anecdotes, outrage, identity loyalty, screenshots, or unnamed insiders.
Examples: "A source close to the investigation says," "People are saying," "Many experts believe" without citations.

**Context Stripping**
Removing dates, geography, denominators, qualifications, or surrounding quotes necessary to understand a claim.

**For each detected pattern, record:**
```json
{
  "pattern": "[pattern name from list above]",
  "quoted_article_language": "[exact quote from article]",
  "why_it_matters": "[how this language affects the reader's ability to evaluate the claim]",
  "severity": "low | medium | high",
  "does_it_affect_factual_reliability": "yes | no | unclear"
}
```

**Important framing rules:**
- Say "this language has the effect of…" — do NOT say "the author intends to…"
- A finding of manipulative framing does NOT make the underlying facts false
- A lack of manipulative framing does NOT make the facts true
- An emotionally intense article with good evidence should score well here
- A neutral-sounding article with fabricated citations should score poorly here
</step_8_framing_analysis>

<step_9_scoring>
**Scoring — produce separate dimensional scores**

Score on a 0–5 scale. Do NOT produce a single composite score — that would obscure important distinctions.

**Score definitions:**
- 5 = strong (well-supported, consistent, no meaningful issues found)
- 4 = mostly strong (minor issues, caveats, or imprecision)
- 3 = mixed (some claims supported, others not; meaningful concerns exist)
- 2 = weak (most claims poorly supported, significant errors or omissions)
- 1 = very weak (pervasive errors, misleading framing, or substantial fabrication)
- 0 = demonstrably unreliable (core claims false, sources fabricated or systematically misrepresented)

**Dimensions:**
- `factual_accuracy` — are the factual claims true?
- `source_support` — do cited sources say what the article claims they say?
- `quote_integrity` — are attributed quotes accurate and in context?
- `numerical_integrity` — are figures, percentages, and statistics correctly used?
- `context_completeness` — does the article provide enough context to interpret claims fairly?
- `rhetorical_transparency` — does the article use language that aids or hinders careful evaluation?
- `overall_reliability` — holistic judgment weighted across all dimensions

**For each score, include:**
```json
{
  "dimension": "",
  "score": 0,
  "confidence": "high | medium | low",
  "basis": "brief explanation of the score"
}
```

If evidence was insufficient to score a dimension reliably, set confidence to `low` and note the reason.
</step_9_scoring>

<step_10_output>
**Final Output — format and present the complete report**

**Default output format (`detailed`):**

```markdown
## Fact-Check Report: [Article Title]

**Publication:** [publication] · **Author:** [author] · **Date:** [date]
**Depth:** [quick|standard|deep] · **Claims checked:** [N of M total]
**Fact-checked on:** [current date]

---

## Overall Assessment

[2–4 sentence summary of what the article gets right, what it gets wrong, and whether its framing is designed to aid or hinder critical thinking. Do not lead with politics. Lead with evidence.]

---

## Key Findings

- [Most important finding — true or false]
- [Second most important finding]
- [Third — continue for all key findings]

---

## Claim-by-Claim Review

| ID | Claim | Type | Verdict | Confidence | Best Source |
|---|---|---|---:|---:|---|
| C001 | … | … | Supported | High | [source] |
| C002 | … | … | Misleading | Medium | [source] |

[For each claim with verdict other than Supported: one paragraph explaining the finding, what the evidence shows, and what would be needed to resolve the question.]

---

## Quote Verification

| ID | Quote (as in article) | Attributed To | Verdict | Source |
|---|---|---|---|---|
| Q001 | "…" | Name | Exact | [link] |
| Q002 | "…" | Name | Truncated misleadingly | [link] |

[For each non-exact quote: explain what was changed and how it affects meaning.]

---

## Numerical Claims

| ID | Article Figure | Finding | Notes |
|---|---|---:|---|
| N001 | 73% of adults | Supported | Matches CDC 2023 dataset |
| N002 | $4.2 trillion | Misleading | Figure is 5 years old; current is $2.8T |

---

## Underlying Source Checks

| Source | Article's Use | Finding | Misrepresentation Type |
|---|---|---|---|
| [Study/report name] | "X proves Y" | Does not support: study found no significant effect | Overstatement |

[For each discrepancy: explain what the article claimed the source shows vs. what it actually shows.]

---

## Critical-Thinking Suppression / Manipulative Framing

| Pattern | Example from Article | Severity | Effect on Reader |
|---|---|---:|---|
| Urgency Pressure | "Share before this is deleted" | High | Discourages verification |

[If no manipulative framing detected, say so clearly.]

---

## Missing Context

[List of factual claims that are technically accurate but require additional context to interpret correctly. For each: what context is missing and why it matters.]

---

## Best Evidence Found

[List the highest-quality sources discovered during fact-checking that bear on the article's main claims.]

---

## Unresolved Questions

[Claims that could not be verified or refuted with available public evidence. For each: what would be needed to resolve it.]

---

## Final Reliability Scores

| Dimension | Score (0–5) | Confidence | Basis |
|---|---:|---:|---|
| Factual Accuracy | 3 | High | … |
| Source Support | 2 | Medium | … |
| Quote Integrity | 4 | High | … |
| Numerical Integrity | 3 | Medium | … |
| Context Completeness | 2 | High | … |
| Rhetorical Transparency | 1 | High | … |
| **Overall Reliability** | **2** | **High** | … |

---

*This report reflects evidence available as of [date]. Some claims may be unverifiable due to paywalls, removed content, or unavailable primary sources.*
```

**For `summary` output format:** Overall Assessment + Key Findings + Final Reliability Scores only.

**For `evidence_table` output format:** Claim-by-Claim Review table + Underlying Source Checks table + Final Reliability Scores only.

**For `json` output format:**
```json
{
  "article": { "title": "", "author": "", "publication": "", "date": "", "url": "" },
  "depth": "",
  "fact_checked_on": "",
  "claims": [],
  "quotes": [],
  "numerical_figures": [],
  "underlying_sources": [],
  "framing_patterns": [],
  "scores": [],
  "missing_context": [],
  "best_evidence": [],
  "unresolved_questions": [],
  "overall_assessment": ""
}
```
</step_10_output>

<step_11_safety_guardrails>
**Safety and Reliability Rules — enforced throughout**

These rules apply at every step, not just at output time.

1. **No defamatory certainty.** Do not state with certainty that a named individual committed a crime, acted fraudulently, or holds a specific belief unless that is strongly supported by primary evidence. Use "alleged," "according to [source]," or "evidence suggests" appropriately.

2. **No allegation as fact.** An accusation is not a finding. A lawsuit is not a conviction. A report is not a verdict. Distinguish these clearly.

3. **Intent language.** Say "this language has the effect of reducing the reader's ability to evaluate the claim" — not "the author intends to deceive." Do not infer intent.

4. **No suppression of minority views.** Do not mark a claim as false merely because it disagrees with consensus. Scientific consensus is relevant evidence; it is not a substitute for examining the specific claim.

5. **No tone-based verdicts.** Emotional intensity does not indicate falsehood. Neutral tone does not indicate accuracy. Evaluate evidence, not style.

6. **Source neutrality.** Do not grant automatic trust to mainstream, government, academic, or alternative sources. Evaluate each source on evidence quality, method transparency, and proximity to primary data.

7. **Evidence rules.** Every factual verdict must cite the source used. "Common knowledge" is not a source. "Obviously true" is not a source.

8. **Conflicting evidence.** When credible sources disagree, name both and describe the disagreement. Do not suppress one side to reach a clean verdict.

9. **Freshness.** For current-event claims, verify that your sources are not outdated. If you cannot confirm a recent date, note the uncertainty.

10. **Scope.** Do not fact-check pure opinion, metaphor, satire, or moral judgment unless they contain an embedded factual assertion.
</step_11_safety_guardrails>

</workflow>

<success_criteria>
- Article text or URL successfully ingested; failure reported clearly if not possible
- All meaningful factual claims extracted with IDs and types
- Claims prioritized correctly for chosen depth level
- Each priority claim has at least one source citation; tier labeled
- Every attributed quote checked against original source
- Every numerical figure checked for units, denominator, timeframe, scope
- Every cited underlying source checked via sub-agent task
- Framing analysis completed with examples and severity ratings
- Scores produced on all seven dimensions with confidence and basis
- Output formatted correctly for chosen output_format
- No defamatory certainty, no allegation treated as proven fact
- Intent language avoided throughout ("has the effect of…" not "intends to…")
- Conflicting evidence named rather than suppressed
- Source tiers labeled on all citations
</success_criteria>

---

## Invocation Examples

### Example 1 — Standard depth, article text supplied

```
User: Can you fact-check this article for me?

[pastes article text about a new climate study]

/article-fact-checker article_text="[pasted text]" depth=standard
```

### Example 2 — Quick check with URL

```
/article-fact-checker article_url="https://example.com/news/story" depth=quick
```

### Example 3 — Deep check with focus area and JSON output

```
/article-fact-checker article_url="https://example.com/health/vaccines" depth=deep user_focus="vaccine efficacy statistics" output_format=json
```

### Example 4 — Called from another skill

A skill that extracts article content from a browser session can hand off to this skill:

```
[After extracting article text and metadata]

Now invoke article-fact-checker with:
- article_text: [extracted body]
- article_title: [extracted title]
- article_author: [extracted byline]
- article_publication: [extracted publication name]
- article_date: [extracted date]
- article_url: [source URL for reference]
- depth: standard
- output_format: detailed
```

The skill returns the full structured fact-check report which the calling skill can present to the user or pass to a downstream summarizer.

---

## Input Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "article-fact-checker input",
  "type": "object",
  "anyOf": [
    { "required": ["article_url"] },
    { "required": ["article_text"] }
  ],
  "properties": {
    "article_url": { "type": "string", "format": "uri" },
    "article_text": { "type": "string", "minLength": 50 },
    "article_title": { "type": "string" },
    "article_author": { "type": "string" },
    "article_publication": { "type": "string" },
    "article_date": { "type": "string" },
    "article_metadata": { "type": "object" },
    "user_focus": { "type": "string" },
    "depth": { "type": "string", "enum": ["quick", "standard", "deep"], "default": "standard" },
    "output_format": { "type": "string", "enum": ["summary", "detailed", "evidence_table", "json"], "default": "detailed" }
  }
}
```

## Output Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "article-fact-checker output",
  "type": "object",
  "required": ["article", "claims", "scores", "overall_assessment"],
  "properties": {
    "article": {
      "type": "object",
      "properties": {
        "title": { "type": "string" },
        "author": { "type": "string" },
        "publication": { "type": "string" },
        "date": { "type": "string" },
        "url": { "type": "string" }
      }
    },
    "depth": { "type": "string" },
    "fact_checked_on": { "type": "string" },
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "claim_text", "claim_type", "verdict", "confidence"],
        "properties": {
          "id": { "type": "string" },
          "claim_text": { "type": "string" },
          "claim_type": { "type": "string" },
          "verdict": { "type": "string", "enum": ["supported","mostly_supported","needs_context","misleading","unsupported","false","unable_to_verify"] },
          "confidence": { "type": "string", "enum": ["high","medium","low"] },
          "sources": { "type": "array" },
          "notes": { "type": "string" }
        }
      }
    },
    "quotes": { "type": "array" },
    "numerical_figures": { "type": "array" },
    "underlying_sources": { "type": "array" },
    "framing_patterns": { "type": "array" },
    "scores": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["dimension", "score", "confidence", "basis"],
        "properties": {
          "dimension": { "type": "string" },
          "score": { "type": "integer", "minimum": 0, "maximum": 5 },
          "confidence": { "type": "string" },
          "basis": { "type": "string" }
        }
      }
    },
    "missing_context": { "type": "array", "items": { "type": "string" } },
    "best_evidence": { "type": "array" },
    "unresolved_questions": { "type": "array", "items": { "type": "string" } },
    "overall_assessment": { "type": "string" }
  }
}
```
