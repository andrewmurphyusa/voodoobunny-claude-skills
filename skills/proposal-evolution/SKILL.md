---
name: proposal-evolution
description: Converts a project proposal into a prompt optimized for the taches create-meta-prompts skill. Use when you have a draft proposal and want to generate a research/plan/implement meta-prompt pipeline. Projects live under the idea-projects-with-tasche folder.  Project prompts should be placed in the prompts/proposal or prompts/ subfolder of the project, and named with a 01*initial*proposal* pattern (e.g. "01 - initial proposal.md"). If no filename is given, this skill will look for files matching that pattern to find the proposal to evolve.
---

<objective>
Transform a rough project proposal into a well-structured prompt ready for the taches "create-meta-prompts" skill. This bridges the gap between an initial idea and a full research -> plan -> implement pipeline.

The skill reads the proposal, understands the create-meta-prompts intake expectations, and produces a revised prompt that will flow smoothly through the meta-prompts workflow. The output includes exact commands to run next.
</objective>

<quick_start>
**Usage:** Invoke with an optional project identifier and an optional proposal filename.

```
/proposal-evolution                                          # use current directory
/proposal-evolution buckeye-consultant                       # named project under idea-projects-with-tasche/
/proposal-evolution buckeye-consultant prompts/my-custom-proposal.md
/proposal-evolution /absolute/path/to/project               # explicit absolute path
/proposal-evolution . prompts/my-custom-proposal.md         # current directory, specific file
```

- **First argument (optional):** One of:
  - Omitted or `.` → use the **current working directory** as the project root
  - An absolute path → use that directory as the project root
  - A plain name (no slashes) → treated as a subfolder under `C:/source code 2/idea-projects-with-tasche/`
- **Second argument (optional):** Relative path (from project root) or absolute path to the proposal file *OR* "latest" to auto-detect the latest user-generated proposal file in the project prompts directory.

- if the second argument is a specific filename and not "latest", the skill will look for that file (first resolving it relative to the project root if it's not an absolute path) and use it as the proposal. If the file does not exist, it will report an error and stop.
- If the second argument is "latest", the skill searches `<project-root>/prompts/proposal/` and then `<project-root>/prompts/` for files matching `[0-9]*[ ].[-].[ ].initial*proposal*` (case-insensitive). If exactly one match is found, it uses that. 
   - If multiple matches are found,, it looks for the highest prefix number "[0-9]*" below 999 and uses that.  
   - If no matches are found, it looks for files matching `initial*proposal*`.  If there are still no matches found, it warns and stops.  
- If no second argument is provided, it behaves as if "latest" was provided. 

The skill will:
1. Resolve the project root to `C:/source code 2/idea-projects-with-tasche/<subfolder>/`
2. Normalize proposal filenames in prompts/proposal/ or prompts/ to the `NNN - initial proposal.md` format if files are numerically prefixed but not in "NNN - "format; if only one "initial-proposal" file is found and it is not prefixed, it will be renamed to "001 - initial proposal.md"
3. If told to use the next numbered file, then find the newest version of the proposal (under 999) and read it.  If not explicitly told that, rename `999 - Prompt as Revised by Claude.md` to the next number and use that as the latest proposal.
4. Analyze the proposal to extract key information and identify any ambiguities or missing details
5. Ask clarifying questions if anything is unclear or contradictory (up to 10 rounds)
6. Save the transcript of the clarifying questions and answers to a file under prompts/clarification (e.g. `prompts/clarification/proposal-clarifications-2024-06-30.md`)
7. Rewrite the proposal as an optimized prompt for create-meta-prompts
8. Write the result to `<project-root>/prompts/999 - Prompt as Revised by Claude.md`, where NNN is the next available 3-digit numeric prefix (e.g. 002, 003, etc.)
9. Print exact commands to run next
</quick_start>

<context>
Projects root: `C:/source code 2/idea-projects-with-tasche/`
Taches skills location: `C:/source code 2/taches-claude-code-resources/`
Create-meta-prompts skill: @C:/source code 2/taches-claude-code-resources/skills/create-meta-prompts/SKILL.md
</context>

<workflow>

<step_1_validate>
**Validate inputs and resolve paths**

Parse the arguments:
- **Arg 1 (optional):** Project identifier — see rules below
- **Arg 2 (optional):** Proposal filename (relative or absolute path)

Resolve the project root using these rules (in order):
1. If Arg 1 is absent or is `.` → `<project-root>` = current working directory
2. If Arg 1 is an absolute path → `<project-root>` = that path
3. If Arg 1 contains no path separators (plain name) → `<project-root>` = `C:/source code 2/idea-projects-with-tasche/<arg1>/`

Validate the project root directory exists. If not, report the error and stop.

**Find the proposal file:**

If arg 2 was provided:
- If it's an absolute path, use it directly
- If it's a relative path, resolve it relative to `<project-root>`
- Validate the file exists. If not, report the error and stop.

If arg 2 was NOT provided:
- Search `<project-root>/prompts/` for files matching the glob pattern `01*initial*proposal*` (case-insensitive)
- Also check for variations like `01 - initial proposal.md`, `01- initial-proposal.md`, `01_initial_proposal.md`, etc.
- **If exactly one match:** Use that file
- **If zero matches:** Report "No proposal file found in `<project-root>/prompts/`. Expected a file matching `01*initial*proposal*`. You can specify the filename explicitly as a second argument." and stop.
- **If multiple matches:** Report "Found multiple proposal files in `<project-root>/prompts/`:" then list them all, and say "Please specify which one to use as the second argument." and stop.

Also check for any other files in `<project-root>/prompts/` that provide additional context.
</step_1_validate>

<step_2_analyze>
**Analyze the proposal**

Read the proposal and extract:
- **Core idea**: What is being built?
- **Problem statement**: What problem does it solve?
- **Target users/audience**: Who is it for?
- **Key features**: What are the main capabilities?
- **Technical hints**: Any technologies, APIs, or approaches mentioned?
- **Constraints**: Any limitations or requirements mentioned?
- **Scope indicators**: Is this a small utility, a full app, a library, etc.?
</step_2_analyze>

<step_3_clarify>
**Clarifying questions loop (up to 10 rounds)**

After analyzing the proposal, identify anything that is unclear, ambiguous, contradictory, or missing important detail. This includes:
- Vague requirements that could be interpreted multiple ways
- Contradictions between different parts of the proposal
- Missing information needed to generate good research/plan/implement prompts
- Unstated assumptions that should be confirmed
- Scope ambiguities (what's in vs out)
- Technical choices that need clarification

**For each round:**

1. Review the proposal content plus all answers gathered so far
2. Generate a numbered list of up to 10 clarifying questions
3. If there are **zero questions** for this round (everything is clear enough), exit the loop and proceed to step 5 (generate)
4. Present the questions to the user as a numbered list, like:

```
**Clarifying questions (round N of up to 10):**

1. [Question about unclear aspect]
2. [Question about contradictory detail]
3. [Question about missing info]
...

Please answer as many as you can. You can skip any that you don't have an answer for yet. When you're done, I'll either ask follow-up questions or proceed to generate the revised prompt.
```

5. Wait for the user's response
6. Incorporate their answers into your understanding of the proposal
7. Continue to the next round (back to step 1 of this loop)

**Loop exit conditions (any of these):**
- No clarifying questions remain for the current round (everything is sufficiently clear)
- 10 rounds have been completed (proceed with what you have)
- The user explicitly says to proceed / skip remaining questions

**Important:** It is perfectly fine to have zero questions on the very first round. If the proposal is clear and complete, skip straight to step 4. Do not ask questions for the sake of asking questions.

When the loop exits, briefly summarize any key clarifications that were gathered (if any) before proceeding.
</step_3_clarify>

<step_4_understand_target>
**Understand create-meta-prompts expectations**

The create-meta-prompts skill expects:
- A clear **purpose** (Research, Plan, or Do) - we want a **Research** prompt first, which chains into Plan, then Do
- A **topic identifier** in kebab-case for file naming
- Enough context for the skill to generate prompts with: objective, context, requirements, output spec, metadata, SUMMARY.md requirement, and success criteria
- References to any existing research/plan files in `.prompts/`

The revised prompt should be written so that when the user invokes `/create-meta-prompts` and pastes it, the skill can:
1. Immediately identify purpose as a multi-stage pipeline (Research -> Plan -> Do)
2. Extract a clear topic identifier
3. Generate a chained set of prompts without needing many follow-up questions
</step_3_understand_target>

<step_5_generate>
**Generate the revised prompt**

Write a revised prompt that includes:

1. **Clear intent statement**: "I want to create a research -> plan -> implement pipeline for [topic]"
2. **Topic identifier**: Suggest a kebab-case identifier
3. **Structured context from the proposal**:
   - Problem being solved
   - What the project should accomplish
   - Key features and requirements
   - Technical approach or constraints (if any)
   - Success criteria
4. **Pipeline specification**:
   - Research phase: What needs to be investigated
   - Plan phase: What decisions and architecture to define
   - Implementation phase: What to build first (MVP/initial task list)
5. **Execution note**: Mention that the user will use their enhanced ralph wiggum loop from `improved-ralph/` for implementation
6. **Output preferences**: Request that prompts include exact commands to run them

The prompt should be self-contained - someone reading it should understand the full project vision without needing the original proposal.
</step_5_generate>

<step_6_write_output>
**Write the output file**

Write the revised prompt to: `<project-root>/prompts/02 - Revised prompt recommended by Claude.md`

At the end of the file, include a section:

```markdown
---

## Commands to run next

### 1. Generate the meta-prompt pipeline
```
cd "<project-root>"
```
Then invoke the create-meta-prompts skill:
```
/create-meta-prompts
```
Paste or reference this file as context when prompted.

### 2. Review the generated prompts
Check the `.prompts/` directory for the generated research, plan, and implement prompts.

### 3. Run the implementation loop
```
cd "<project-root>"
```
Use the enhanced ralph wiggum loop:
```
/setup-ralph
```
```
</step_6_write_output>

<step_7_report>
**Report results**

Print:
- Confirmation that the file was written
- A brief summary of what was extracted from the proposal
- The exact path to the output file
- The commands to run next (same as written in the file)

**Do NOT offer to perform any follow-up actions.** Just present the results and commands.
</step_7_report>

</workflow>

<success_criteria>
- Project root resolved correctly under idea-projects-with-tasche/
- Proposal file found (auto-detected or explicitly specified)
- Proposal file was read and understood
- Clarifying questions asked if proposal had ambiguities (or skipped if clear)
- User answers incorporated into the revised prompt
- Revised prompt is well-structured for create-meta-prompts intake
- Topic identifier is clear and in kebab-case
- Pipeline stages (research/plan/implement) are specified
- Output file written to correct location
- Exact runnable commands included
- No follow-up actions offered
</success_criteria>
