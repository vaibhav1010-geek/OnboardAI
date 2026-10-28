# Onboarding Assistant: PRD, Risk Register and Roadmap

*Author: Vaibhav Gupta | Status: v1 built as a demo | Last updated: 27-10-26*


---

# Part 1: Product Requirements (PRD)

## 1. Summary

An AI assistant that answers new-hire questions from company documents with citations, hands sensitive topics to HR, and raises tool-access requests in Jira only after the employee confirms. Built for a fictional company (Acme Demo Co) using 11 synthetic policy documents.

## 2. Problem

In their first weeks, new hires ask the same questions (leave, benefits, VPN, tool access). HR and IT answer them repeatedly, and access requests stall when they reach the wrong queue.

**Evidence:**  This demo has not been measured with real employees yet.

## 3. Users

- **Primary:** new employees in their first 30 days.
- **Secondary:** People Team (HR) and IT, who approve requests and answer escalations.
- **Not for v1:** managers, contractors, multiple countries or languages.

## 4. Goals and non-goals

**Goals**

1. Answer policy questions correctly, with a source the user can check.
2. Never guess: say it could not find the answer and point to a contact.
3. Hand sensitive topics (pay negotiation, visas, harassment, health, legal) to a human.
4. Create access requests only after the user confirms and the role check passes.

**Non-goals**

- Granting access (a human approver does that).
- Answering personal HR cases or anything needing live payroll or HR data.
- Replacing the People Team.

## 5. User stories

| As a... | I want to... | So that... |
| --- | --- | --- |
| New hire | Ask how many leave days I get | I do not have to find the policy PDF |
| New hire | See which document an answer came from, and its date | I can trust it or check it |
| New hire | Request GitHub access in one conversation | I do not have to find the right form or approver |
| New hire | Be told clearly when the bot does not know | I contact the right person instead of acting on a guess |
| HR | Have sensitive messages routed to me, not answered by a bot | Employees get human care on personal matters |
| IT approver | Receive complete tickets with tool, role and reason | I can approve quickly |

## 6. Functional requirements

1. **Cited answers.** Answers grounded in retrieved documents should cite the relevant passages as \[1\], \[2\] and show the source title, section and last-updated date. The release target for citation coverage is at least 95%.
2. **Refusal over guessing.** A similarity threshold filters weak matches. With no relevant document, the bot says it could not find the answer and gives the HR or IT contact.
3. **Stale and conflicting documents.** Documents older than 365 days are flagged. If two documents disagree, the bot shows both with dates and prefers the newer.
4. **Sensitive topics.** A keyword safety net sends a fixed HR handoff with no model call. The system prompt also tells the model to refer paraphrased sensitive messages to HR.
5. **Access requests.** The bot gathers the tool and a business reason. The role rule is enforced in code. A confirmation card shows tool, approver, turnaround and an editable reason. A ticket is created in Jira (through an MCP server) only after the user clicks confirm. Repeat clicks do not create duplicates. The bot always says it is a request, not a grant.
6. **Audit log.** Searches, escalations and ticket actions are recorded for later analysis.
7. **Injection resistance.** Instructions inside documents or user messages cannot override the rules or reveal the system prompt.

## 7. Key product decisions

| Decision | Choice | Why | Tradeoff |
| --- | --- | --- | --- |
| Auto-create tickets or ask first | Ask first (confirmation card) | Trust in new AI tools is low, and an access request is consequential | One extra click |
| Where role rules live | Enforced in code, with the rules also in the prompt | Code gives a guarantee. The prompt makes the conversation honest | A prompt-only version offered requests the role could not make |
| Sensitive topics | Keyword net plus model judgement | Keywords are predictable. The model catches paraphrases | Keywords miss rewording, so the model must catch it |
| Unknown answers | Say it could not find it | A wrong policy answer is worse than none | Some answerable questions get a refusal |
| Jira access | Called by our code after approval, not exposed to the model | Keeps the confirmation guarantee | Less flexible than letting the agent use any Jira tool |
| Model | Current evaluation and demo model: gpt-oss-120b on Groq | Used for the latest full 90-case evaluation | Results are specific to this model and configuration; re-evaluate after a model change |
| Re-indexing | Manual button and command | Simplest for v1 | Documents can go stale until someone re-indexes |

## 8. Success metrics and release thresholds

Thresholds are set by risk: safety behaviors must be near-perfect, answer quality can be lower.

| Metric | Release target | Latest result |
| --- | --- | --- |
| Access request shown for confirmation before any ticket | 100% | 7/7 (100%); no-bypass check passed 1/1 |
| Sensitive topic handed to a human | 100% target | Keyword cases 10/10; paraphrased sensitive cases 5/5 |
| Correct refusal when not in the documents | 95%+ | 12/12 (100%) |
| Factual answers correct | 90%+ | 30/31 (96.8%) |
| Answers carry citations | 95%+ | 48/49 (98.0%) |
| Retrieval fetched the right document | 95%+ | 49/49 (100%) |
| Normal questions wrongly escalated | under 5% | 0/49 (0%) |
| Deflection rate, time-to-access, satisfaction | Not set for this demo | Not measured; requires a real-user pilot and the deferred analytics feature |

## 9. Quality evidence: how it was evaluated

**Method.** The current suite has 90 cases: 70 core cases and 20 harder cases (typos, vague wording, paraphrased sensitive messages, and roundabout permission requests). Categories cover facts, multi-document questions, conflicting documents, not-in-documents, escalation, access requests and denials, prompt injection, and false escalation. Scoring is rule-based and has separate offline tests. The complete result below is saved in [`results/20261027_155338_full.md`](./results/20261027_155338_full.md); the run records the model and configuration. Historical reports used older question-set sizes and should not be compared as if they were the same suite.

**Latest full result (27 October 2026)**

| Run | Model | Result |
| --- | --- | --- |
| Full current set (70 core + 20 hard) | openai/gpt-oss-120b, temperature 0.1 | 87/90 passed (96.7%) |

**Category and safety results**

| Category or metric | Result |
| --- | --- |
| Facts | 30/31 (96.8%) |
| Conflicting documents | 4/5 (80.0%) |
| Multi-document / multi-intent | 9/10 (90.0%) |
| Access confirmation | 6/6 cases; 7/7 confirmation-card checks |
| Access denial | 5/5 |
| Sensitive escalation | 10/10 standard escalation and 5/5 paraphrased escalation |
| Unanswerable questions | 12/12 |
| Retrieval hit rate | 49/49 (100%) |
| Citation rate | 48/49 (98.0%) |
| Correct escalation rate | 10/10 (100%) |
| False escalation rate | 0/49 (0%) |

**Failures requiring follow-up**

1. **F25 — VPN answer failed a literal wording check.** The answer says VPN "isn’t enabled by default" and that an access request must be submitted, conveying the expected meaning. The scorer expects the literal substring "not", so the contraction caused a likely rubric false negative. Review the rubric and answer; change scoring only if the expected behavior is still measured, and keep the case as a regression test.
2. **H02 — Expense answer omitted required details.** The answer gives the Rs 800 limit and receipt condition but does not name ExpenseDesk, which the case expects. It also does not explain the superseded Rs 600 figure. Make the current submission location explicit and check that the answer handles the outdated value accurately.
3. **H06 — Multi-intent access question returned no final answer.** The run searched policies and called the access-request tool, but the recorded final answer was empty. Investigate how a request requiring confirmation is handled when combined with a second policy question, and add a regression check that both parts receive a clear response.

**Limitations.** Small synthetic test set written by the builder; single-turn cases (including multi-intent inputs) rather than multi-turn conversation evaluation; rule-based checks can pass an answer with the right keyword and an invented extra claim; provider limits can interrupt runs; no real users yet. A 96.7% score is evidence about this test set and configuration, not proof of production readiness.

## 10. Decisions and pilot gates

- **Pilot scope:** No real-user pilot is approved by this document. Before one begins, product and HR/IT owners must agree on participants, success criteria, and escalation handling.
- **Analytics:** Deflection, time-to-access, satisfaction, thumbs feedback, and an admin-only Insights view are deferred to a later version; none is measured by this eval suite.
- **Content sources:** The current demo uses 11 synthetic Markdown policies. Additional sources such as Drive, Confluence, and complex PDFs are not supported or validated for this release.
- **Privacy:** Before any real employee data is processed, Security and Product must approve what is sent to model providers or LangSmith, redaction, access, and retention.
- **Release gate:** Do not use the synthetic eval score alone to authorize production use. Resolve the three failures above, run the current 90-case suite again, and complete the pilot and privacy decisions before expanding beyond the demo.

---

# Part 2: Risk Register

Likelihood and impact: L = low, M = medium, H = high.

| ID | Risk | Likelihood | Impact | Mitigation in place | Gap or next action | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | Wrong answer from a stale or conflicting document | M | H | Outdated flag and newer-source preference; latest conflict category scored 4/5 | Review H02's current-vs-outdated limit handling and retire superseded documents at source | People Team |
| R2 | Bot guesses when the answer is not in the documents | M | H | Similarity threshold, refusal rule, 12 not-in-documents tests | Tune threshold on real questions | Product |
| R3 | Answer omits a required fact, especially in a multi-intent request | M | H | Latest retrieval hit rate is 49/49; citations 48/49; fact and multi categories scored 30/31 and 9/10 | Fix or explain F25, H02, and H06; add focused regression tests before pilot | Engineering and Product |
| R4 | Sensitive topic answered instead of handed off | L | H | Keyword net, model instruction, 15 test cases | Keywords miss rewording, so grow the paraphrase tests | Product |
| R5 | Unauthorized or accidental access request | L | H | Role check in code, confirmation card, human approver, duplicate prevention, skip-confirmation test | Add approver-side audit review | Engineering and IT |
| R6 | Prompt injection through user messages or documents | L | M | Documents treated as data, 2 injection tests, 1 bypass test | No test with injected text inside a document yet | Engineering |
| R7 | Employee data ends up in logs or LangSmith traces | M | M | Synthetic data only for now | Decide what is traced, redaction and retention before real use | Product and Security |
| R8 | Provider rate limits or outage | H | M | Current model is gpt-oss-120b; retries and clean stop on daily quota | Confirm provider capacity and operating plan before any pilot; do not assume a fallback is configured | Engineering |
| R9 | Eval blind spots (grader errors, small synthetic set) | H | M | Separate offline scorer tests; full report includes three failures for manual review | Review F25 against rubric; add real-user failures only after approved pilot and privacy controls | Product |
| R10 | Users treat the bot as final authority | M | M | Citations with dates, request-only wording, contacts shown | Keep the demo clearly labeled; review wording and monitor during any approved pilot | Product |
| R11 | Real documents break ingestion (PDF tables, scans, Word) | H | M | Markdown, text and PDF text supported | Stress test on real handbook pages; add OCR and table handling | Engineering |

---

# Part 3: Roadmap

## Now (built)

- Cited answers with refusal, outdated-document flags and conflict handling
- Sensitive-topic handoff (keyword net plus model judgement)
- Role-checked access requests with confirmation and Jira ticket creation through MCP
- Current 90-case eval suite (70 core + 20 hard), LangSmith dataset/experiment support, and offline scorer checks; latest full run is 87/90 (96.7%) on gpt-oss-120b

## Next

| Item | Why | Success looks like |
| --- | --- | --- |
| Resolve the three latest full-suite failures (F25, H02, H06) | Latest full run passed 87/90; includes a likely wording-rubric mismatch, missing ExpenseDesk detail, and a missing final answer | Each case is manually reviewed; any answer or scorer change is justified; all three regression checks pass and a new full run has no unexplained failures |
| Pilot planning and approval | Synthetic tests do not establish real-world usefulness or deflection | Product and HR/IT approve participants, success criteria, and operating process before a pilot starts |
| Privacy and trace review | Real employee content may be sensitive | Security and Product approve data handling, provider sharing, access, redaction, and retention before a pilot |
| Test on representative documents | Demo currently uses synthetic Markdown, not real handbooks | Approved sample documents are evaluated for ingestion, retrieval, citations, and stale/conflict handling |
| Add feedback and admin-only Insights in a later version | Deflection, unanswered-question trends, and satisfaction are not measured | Analytics requirements, definitions, access control, and privacy are agreed before implementation |
| Retrieval evaluation (for example Ragas) | Separate retrieval issues from answer-generation issues | Retrieval and faithfulness measures are validated against a reviewed dataset before being used as release gates |

## Later

- Connectors (Google Drive, Confluence) with automatic re-indexing
- Hybrid keyword plus meaning search and a reranker
- Role-based document access
- Multi-turn conversation evals
- Slack entry point and proactive checklist nudges
- Admin-only HR/IT dashboard of top questions and documentation gaps (after access control and privacy review)

## Not planned

- Granting access automatically
- Handling pay, visa, legal or health cases
