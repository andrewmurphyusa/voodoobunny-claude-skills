---
name: facebook-article-fact-checker-adapter
description: Facebook-specific adapter that extracts and normalizes article content shared via Facebook posts, then delegates to the generic article-fact-checker skill. Handles Facebook post URLs, copied post text, screenshots, and manually provided article links. Adds a Facebook-specific framing analysis layer that evaluates whether the post misrepresents, exaggerates, or adds claims beyond the linked article. Use when the user wants to fact-check an article they encountered on Facebook, or when they want to know whether the Facebook post itself adds misleading framing.
---

<objective>
Extract article content and framing from a Facebook post — whether provided as a URL, pasted text, screenshot, or manually supplied link — then pass the normalized article to the generic `article-fact-checker` skill for rigorous fact-checking.

Separately analyze the Facebook post's own framing: does the post accurately represent the article it shares, or does it add exaggeration, false context, urgency language, or unsupported claims?

Return a combined report that clearly distinguishes:
- What the Facebook post claims
- What the linked article claims
- What the generic fact-checker found about the article
- Whether the Facebook post adds misleading framing beyond the article itself

This skill is an adapter. It does not reimplement fact-checking logic. All factual claim verification, quote checking, numerical verification, source checking, and reliability scoring are delegated to `article-fact-checker`.
</objective>

<quick_start>
**Usage:** Invoke with at least one Facebook-related input.

```
/facebook-article-fact-checker-adapter                                   # prompts for input
/facebook-article-fact-checker-adapter facebook_post_url="https://..."  # Facebook post URL
/facebook-article-fact-checker-adapter article_url="https://..."        # article URL extracted manually
/facebook-article-fact-checker-adapter depth=quick                      # quick pass on top claims
/facebook-article-fact-checker-adapter include_comments_context=true    # include comments if visible
/facebook-article-fact-checker-adapter output_format=json               # machine-readable output
```

**At least one of the following must be provided:**

| Field | Type | Description |
|---|---|---|
| `facebook_post_url` | string | Direct URL to the Facebook post |
| `facebook_post_text` | string | Copied text of the Facebook post |
| `screenshot_paths` | array | Local paths to one or more post screenshots |
| `article_url` | string | Article URL extracted manually from the post |

**Optional fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `include_post_framing_analysis` | boolean | `true` | Analyze whether the post misrepresents the article |
| `include_comments_context` | boolean | `false` | Include visible comments in framing context |
| `depth` | enum | `standard` | `quick` · `standard` · `deep` — passed to article-fact-checker |
| `output_format` | enum | `detailed` | `summary` · `detailed` · `json` |

**If none of the required inputs are provided**, ask the user to supply at least one. Do not proceed without input.
</quick_start>

<context>
This skill delegates all article fact-checking to:
`skills/article-fact-checker/SKILL.md`

The separation of responsibilities is strict:

**This adapter handles:**
- Input intake from Facebook-specific sources
- Link extraction and URL expansion
- Screenshot and pasted text parsing
- Authentication boundary documentation
- Privacy and consent safeguards
- Normalization of extracted content into the article-fact-checker input format
- Facebook-specific post framing analysis
- Combined output assembly

**`article-fact-checker` handles:**
- Claim extraction
- Fact verification
- Quote checking
- Numerical verification
- Underlying source checking
- Manipulative language analysis
- Final reliability scoring

**What this skill does NOT do:**
- Does not post, comment, react, like, share, or message on Facebook
- Does not bypass Facebook access controls, paywalls, or group privacy
- Does not collect or store Facebook credentials
- Does not scrape private content without user authorization
- Does not access content not visible to the user
- Does not retain screenshots after processing unless explicitly requested
- Does not perform political persuasion analysis beyond factual framing assessment
- Does not surveil individuals, groups, or feeds
</context>

<authentication_boundary>
## Authentication Boundary

**Safest mode — no authentication required:**
The safest and recommended approach is for the user to supply the article URL directly, paste the Facebook post text, or paste the article text. No Facebook account access is needed.

**Browser-assisted extraction — optional, explicit consent required:**
If the user wants to extract content from a Facebook post URL directly, a local browser session may be used. This requires:
- The user must explicitly enable and configure local browser access
- The user must be already logged in to Facebook in that browser profile
- The user must understand that browser-assisted access can read anything their account can normally see
- The user must consent to this mode before it is used

**This skill will never:**
- Ask for or store the user's Facebook password or session tokens
- Request Facebook API credentials
- Access private groups, restricted posts, or deleted content
- Bypass any Facebook access control
- Send private Facebook post content to external services unless the user explicitly approves this and the destination is clearly documented

**If browser-assisted extraction is not configured**, the skill falls back to the user-provided text or screenshot mode and asks the user to supply the article link or text manually.
</authentication_boundary>

<workflow>

<step_1_intake>
**Intake — validate inputs and determine access mode**

Check which inputs are present:

1. `facebook_post_url` — direct post URL
2. `facebook_post_text` — pasted post text
3. `screenshot_paths` — one or more screenshot files
4. `article_url` — article URL extracted manually by the user

**If none are present:**
> "Please provide at least one of: a Facebook post URL, copied Facebook post text, a screenshot path, or the article URL from the post. I cannot proceed without input."
Then stop and wait.

**Determine access mode (in priority order):**

- **Mode A — User-Provided Article URL**
  Use when `article_url` is set. This is the simplest and safest mode.
  The Facebook post context comes from `facebook_post_text` or `screenshot_paths` if present.

- **Mode B — Copied Facebook Text**
  Use when `facebook_post_text` is set. Extract the article URL from the pasted text.
  If no URL is found in the text, ask the user to provide the article link separately.

- **Mode C — Screenshot-Based Extraction**
  Use when only `screenshot_paths` are provided. Apply vision extraction to identify:
  - Visible post text
  - Visible shared article headline and description
  - Any visible article URL
  If the article URL is not visible in the screenshot, ask the user to provide it.

- **Mode D — Facebook Post URL (Browser-Assisted)**
  Use only if the user has explicitly configured a local browser session.
  Before proceeding, confirm: "This mode requires a locally configured browser session with your Facebook account. Do you want to proceed?"
  If the user declines or this is not configured, fall back to Mode A/B/C.

Print intake confirmation:
```
Facebook Adapter — Intake Complete
Access mode: [A|B|C|D]
Facebook post text available: [yes/no]
Shared article URL found: [url or "not yet"]
Screenshot(s): [N files or "none"]
```

Proceed automatically.
</step_1_intake>

<step_2_facebook_extraction>
**Facebook Post Extraction — extract all visible post elements**

Using the available input (pasted text, screenshot, or browser session), extract:

```json
{
  "facebook_post_url": "",
  "poster_name_visible": "",
  "post_text": "",
  "post_timestamp_visible": "",
  "shared_article_url": "",
  "shared_article_title_visible": "",
  "shared_article_description_visible": "",
  "visible_reactions_or_engagement": "",
  "visible_comments_context": "",
  "extraction_method": "url | pasted_text | screenshot | browser_session",
  "extraction_confidence": "high | medium | low"
}
```

**URL handling:**
- If the shared article URL is shortened (bit.ly, fb.me, t.co, etc.), expand it safely using `WebFetch` to follow redirects.
- Record both the original shortened URL and the final destination URL.
- Do not follow redirects to domains that appear to be tracking pixels, ad networks, or malware.

**Privacy rules:**
- Include only the poster name if it is relevant to evaluating the post's framing (e.g., if the poster is a public figure or organization making the claim).
- For private individuals, record only "private individual" unless the user specifically requests the name for analysis purposes.
- If `include_comments_context` is false, omit `visible_comments_context` entirely.
- Do not extract or retain information about people who appear only in comments.

**If the shared article URL cannot be found:**
> "I could not find a shared article URL in the provided Facebook post. Please either:
> 1. Paste the article URL directly
> 2. Paste the article text
> 3. Provide a clearer screenshot that shows the article link"
Then stop and wait.

**Extraction confidence:**
- `high` — full post text available, article URL confirmed and expanded
- `medium` — partial text or URL extracted from screenshot, some ambiguity
- `low` — only screenshot available, text or link not clearly visible
</step_2_facebook_extraction>

<step_3_article_retrieval>
**Article Retrieval — fetch the shared article**

Once a shared article URL is available:

1. Attempt to retrieve the article content using `WebFetch`
2. Extract: title, author, publisher, publication date, and full article body
3. Record the final URL after any redirects
4. If the article is behind a paywall or cannot be retrieved, report clearly:
   > "The article at [URL] could not be retrieved: [reason]. Please paste the article text directly so fact-checking can proceed."
   Then stop and wait for the user to provide text.
5. If retrieval partially succeeds (title and metadata but no body), report what was retrieved and ask for the full text.

Record:
```json
{
  "article_url_original": "",
  "article_url_final": "",
  "article_title": "",
  "article_author": "",
  "article_publication": "",
  "article_date": "",
  "article_text": "",
  "retrieval_status": "success | partial | failed",
  "retrieval_notes": ""
}
```

Print confirmation:
```
Article Retrieval Complete
Title: [title]
Author: [author]
Publication: [publication]
Date: [date]
Retrieval status: [success|partial|failed]
```

Proceed automatically.
</step_3_article_retrieval>

<step_4_delegate_to_fact_checker>
**Delegate to article-fact-checker — pass normalized content**

Invoke the `article-fact-checker` skill with the following payload:

```json
{
  "article_url": "[article_url_final]",
  "article_text": "[article_text]",
  "article_title": "[article_title]",
  "article_author": "[article_author]",
  "article_publication": "[article_publication]",
  "article_date": "[article_date]",
  "article_metadata": {
    "source": "facebook-adapter",
    "facebook_post_url": "[facebook_post_url]",
    "shared_article_title_visible": "[shared_article_title_visible]",
    "shared_article_description_visible": "[shared_article_description_visible]"
  },
  "user_focus": "Fact-check article shared via Facebook. Also note whether the Facebook post framing changes or exaggerates the article.",
  "depth": "[depth from input, default standard]",
  "output_format": "detailed"
}
```

Execute the full `article-fact-checker` workflow as documented in `skills/article-fact-checker/SKILL.md`.

Capture the complete fact-check report for inclusion in the combined output.

Do not reimplement any part of the fact-checking workflow here. The entire claim extraction, evidence gathering, quote verification, numerical verification, underlying source checking, framing analysis, and reliability scoring are handled by `article-fact-checker`.
</step_4_delegate_to_fact_checker>

<step_5_facebook_framing_analysis>
**Facebook-Specific Framing Analysis — evaluate the post independently from the article**

This step analyzes the Facebook post text and visible metadata separately from the article content. Apply this only when `include_post_framing_analysis` is true (the default).

**Comparison axes:**

1. **Post claim vs. article claim** — Does the post accurately represent what the article argues?
2. **Post headline/preview vs. article body** — Does the visible Facebook preview match what the article actually says?
3. **Poster's framing vs. article evidence** — Does the poster add claims, judgments, or interpretations not supported by the article?
4. **Caption vs. linked source** — Does the poster's caption introduce unsupported assertions?
5. **Context stripping** — Does the post omit caveats, qualifications, or important context present in the article?
6. **Claim addition** — Does the post introduce claims entirely absent from the article?
7. **Urgency or suppression patterns** — Does the post use language designed to prevent reflection before sharing?

**Important analytical distinctions:**
- The article may be accurate while the Facebook post misrepresents it.
- The Facebook post may be reasonable while the article contains errors.
- The headline or preview may be misleading even if the article body is more careful.
- A user's caption may add unsupported claims beyond what the article states.
- Emotional language in the post is not automatically manipulative — evaluate only language that obscures reasoning or suppresses verification.

**Use the same rhetoric categories as `article-fact-checker` step 8, applied only to the Facebook post text:**
- Certainty Inflation
- Outgroup Contamination
- Epistemic Bullying
- Urgency Pressure
- Conspiracy Sealing
- Motte-and-Bailey Framing
- Loaded Question / Presupposition
- Scapegoating / Dehumanization
- False Binary
- Evidence Substitution
- Context Stripping

**For each framing issue, record:**
```json
{
  "issue_type": "[framing pattern or comparison axis]",
  "facebook_text": "[exact text from the post]",
  "article_text_for_comparison": "[relevant article passage or summary]",
  "severity": "low | medium | high",
  "notes": "[how this affects the reader's ability to evaluate the shared article]"
}
```

**Do not say the poster "intends to deceive."** Say "this framing has the effect of…"

**If the post accurately represents the article**, say so clearly. Do not manufacture framing issues.
</step_5_facebook_framing_analysis>

<step_6_combined_output>
**Combined Output — assemble and format the final report**

**Default output format (`detailed`):**

```markdown
## Facebook Article Fact-Check

**Checked on:** [current date]
**Extraction method:** [mode A/B/C/D — description]
**Extraction confidence:** [high|medium|low]
**Depth:** [quick|standard|deep]

---

### Bottom Line

[2–4 sentences. Lead with what matters most: whether the article is reliable, whether the Facebook post accurately represents it, and what the user should know before sharing. Do not lead with politics.]

---

### What the Facebook Post Claims

[Exact or close paraphrase of the post text. If a caption was added by the poster, quote it directly. Note the visible headline and description preview if present.]

---

### What the Linked Article Claims

[1–3 sentence summary of the article's central argument and key evidence. This is a summary, not a verdict.]

---

### Difference Between Facebook Framing and Article Content

[Describe any gaps, additions, or distortions between what the post implies and what the article actually says. If the post accurately represents the article, say so explicitly.]

---

### Generic Article Fact-Check Result

[Full output from article-fact-checker, embedded here. Preserve all sections: Overall Assessment, Key Findings, Claim-by-Claim Review, Quote Verification, Numerical Claims, Underlying Source Checks, Manipulative Framing, Missing Context, and Final Reliability Scores.]

---

### Facebook-Specific Framing Issues

| Issue | Facebook Text | Severity | Notes |
|---|---|---:|---|
| [issue type] | "[post text]" | [low/medium/high] | [effect on reader] |

[If no framing issues found: "The Facebook post appears to represent the article accurately. No misleading framing patterns detected."]

---

### Extracted Metadata

| Field | Value |
|---|---|
| Facebook post URL | |
| Poster | |
| Post timestamp | |
| Shared article URL | |
| Article title (in Facebook preview) | |
| Article title (actual) | |
| Article author | |
| Article publication | |
| Article date | |
| Extraction method | |
| Extraction confidence | |

---

### Confidence and Limitations

[Note any factors that limit the reliability of this analysis: inaccessible article, low-confidence screenshot extraction, missing post text, etc.]

---

### Recommended User Action

[One to three sentences. Examples:
- "The article is mostly accurate, but the Facebook caption exaggerates the study's conclusions. The original paper explicitly warns against the causal interpretation the post implies."
- "The article's central claim is unsupported by the cited study. Consider not sharing until a more reliable source is found."
- "The post uses urgency language designed to discourage verification before sharing. The article itself is more measured."
- "Both the article and the post appear to represent the evidence accurately. No significant issues found."
- "Unable to fully verify because the article text was not accessible. The fact-check is based on partial metadata only."]
```

**For `summary` output format:** Bottom Line + Difference Between Facebook Framing and Article Content + Final Reliability Scores only.

**For `json` output format:**

```json
{
  "facebook_extraction": {
    "facebook_post_url": "",
    "poster_name_visible": "",
    "post_text": "",
    "post_timestamp_visible": "",
    "shared_article_url": "",
    "shared_article_title_visible": "",
    "shared_article_description_visible": "",
    "visible_reactions_or_engagement": "",
    "visible_comments_context": "",
    "extraction_method": "",
    "extraction_confidence": ""
  },
  "article_fact_check": {},
  "facebook_framing_analysis": {
    "post_accurately_represents_article": true,
    "issues": []
  },
  "combined_assessment": "",
  "limitations": [],
  "recommended_user_action": ""
}
```
</step_6_combined_output>

<step_7_privacy_and_safety>
**Privacy and Safety Enforcement — apply throughout all steps**

These rules apply at every step, not just at output time.

1. **No credential storage.** Do not ask for, accept, or store Facebook passwords, session tokens, cookies, or API keys.

2. **Screenshot retention.** Do not retain screenshot files after processing unless the user explicitly requests retention.

3. **Comments context.** Do not extract or include comments unless `include_comments_context` is true.

4. **Private individuals.** Do not analyze, name, or describe private individuals beyond what is necessary to evaluate the shared article.

5. **Private content.** Do not expose private post content, group content, or restricted content in logs or outputs.

6. **External service transmission.** Do not send private Facebook post content to external services (web APIs, AI endpoints, search engines) unless the user has explicitly approved and the destination is clearly documented in the output.

7. **Browser profile access.** If browser-assisted extraction is used, document what was accessed and why in the output. Do not silently use browser state.

8. **No platform interference.** Do not post, comment, react, like, share, message, or modify anything on Facebook at any step.

9. **No access control bypass.** Do not attempt to access content that requires authentication the user has not already established, or content behind group privacy, age gates, or geographic restrictions.

10. **Defamation rules.** Apply the same defamation rules as `article-fact-checker`: do not state with certainty that a named individual committed a crime or acted fraudulently without primary evidence. Use "alleged," "according to [source]," or "evidence suggests."
</step_7_privacy_and_safety>

</workflow>

<success_criteria>
- At least one valid input accepted; failure reported clearly if none provided
- Access mode determined and documented
- Facebook post text extracted with confidence level
- Shared article URL found, expanded if shortened, and recorded
- Article content retrieved or user asked for paste if retrieval fails
- Full `article-fact-checker` workflow executed; complete report captured
- Facebook-specific framing analysis completed when `include_post_framing_analysis` is true
- Combined report assembled with all required sections
- Privacy rules enforced throughout (no credentials, no private content in logs)
- Authentication boundary documented
- Recommended user action provided
- Output format matches `output_format` parameter
- No fact-checking logic reimplemented in this adapter
</success_criteria>

---

## Invocation Examples

### Example 1 — User provides article URL directly

```
/facebook-article-fact-checker-adapter article_url="https://example.com/health/coffee-study" facebook_post_text="SHARE THIS: New study proves coffee CURES Alzheimer's!! Doctors don't want you to know!"
```

The adapter uses the article URL directly (Mode A), extracts the post text framing, delegates fact-checking to `article-fact-checker`, and returns a combined report noting the gap between the post's claim ("cures," "doctors don't want you to know") and what the study actually found.

### Example 2 — User provides only a Facebook post URL

```
/facebook-article-fact-checker-adapter facebook_post_url="https://www.facebook.com/permalink/12345"
```

The adapter attempts browser-assisted extraction (Mode D) if configured, or asks the user to paste the post text or article link.

### Example 3 — Screenshot-only

```
/facebook-article-fact-checker-adapter screenshot_paths=["C:/screenshots/fb-post.png"]
```

The adapter extracts visible text and links from the screenshot (Mode C), identifies the article URL if visible, and proceeds. If the article URL is not visible, asks the user to provide it.

### Example 4 — Deep check with comments

```
/facebook-article-fact-checker-adapter facebook_post_text="..." article_url="https://..." depth=deep include_comments_context=true output_format=json
```

### Example 5 — Called from another workflow

Another skill or process can invoke the adapter by setting inputs programmatically:

```
Invoke facebook-article-fact-checker-adapter with:
- facebook_post_text: [extracted post text]
- article_url: [extracted article URL]
- depth: standard
- include_post_framing_analysis: true
- output_format: detailed
```

---

## Input Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "facebook-article-fact-checker-adapter input",
  "type": "object",
  "anyOf": [
    { "required": ["facebook_post_url"] },
    { "required": ["facebook_post_text"] },
    { "required": ["screenshot_paths"] },
    { "required": ["article_url"] }
  ],
  "properties": {
    "facebook_post_url": { "type": "string", "format": "uri" },
    "facebook_post_text": { "type": "string", "minLength": 1 },
    "screenshot_paths": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1
    },
    "article_url": { "type": "string", "format": "uri" },
    "include_post_framing_analysis": { "type": "boolean", "default": true },
    "include_comments_context": { "type": "boolean", "default": false },
    "depth": {
      "type": "string",
      "enum": ["quick", "standard", "deep"],
      "default": "standard"
    },
    "output_format": {
      "type": "string",
      "enum": ["summary", "detailed", "json"],
      "default": "detailed"
    }
  }
}
```

## Output Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "facebook-article-fact-checker-adapter output",
  "type": "object",
  "required": ["facebook_extraction", "article_fact_check", "combined_assessment", "recommended_user_action"],
  "properties": {
    "facebook_extraction": {
      "type": "object",
      "required": ["extraction_method", "extraction_confidence"],
      "properties": {
        "facebook_post_url": { "type": "string" },
        "poster_name_visible": { "type": "string" },
        "post_text": { "type": "string" },
        "post_timestamp_visible": { "type": "string" },
        "shared_article_url": { "type": "string" },
        "shared_article_title_visible": { "type": "string" },
        "shared_article_description_visible": { "type": "string" },
        "visible_reactions_or_engagement": { "type": "string" },
        "visible_comments_context": { "type": "string" },
        "extraction_method": {
          "type": "string",
          "enum": ["url", "pasted_text", "screenshot", "browser_session"]
        },
        "extraction_confidence": {
          "type": "string",
          "enum": ["high", "medium", "low"]
        }
      }
    },
    "article_retrieval": {
      "type": "object",
      "properties": {
        "article_url_original": { "type": "string" },
        "article_url_final": { "type": "string" },
        "article_title": { "type": "string" },
        "article_author": { "type": "string" },
        "article_publication": { "type": "string" },
        "article_date": { "type": "string" },
        "retrieval_status": {
          "type": "string",
          "enum": ["success", "partial", "failed"]
        },
        "retrieval_notes": { "type": "string" }
      }
    },
    "article_fact_check": {
      "type": "object",
      "description": "Full output object from article-fact-checker skill"
    },
    "facebook_framing_analysis": {
      "type": "object",
      "properties": {
        "post_accurately_represents_article": { "type": "boolean" },
        "issues": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["issue_type", "facebook_text", "severity"],
            "properties": {
              "issue_type": { "type": "string" },
              "facebook_text": { "type": "string" },
              "article_text_for_comparison": { "type": "string" },
              "severity": {
                "type": "string",
                "enum": ["low", "medium", "high"]
              },
              "notes": { "type": "string" }
            }
          }
        }
      }
    },
    "combined_assessment": { "type": "string" },
    "limitations": {
      "type": "array",
      "items": { "type": "string" }
    },
    "recommended_user_action": { "type": "string" }
  }
}
```
