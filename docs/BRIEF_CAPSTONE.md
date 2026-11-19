# Capstone brief (summary)

**Read this before starting any ticket** (owner's rule, 2026-11-19: the Capstone brief is the primary brief from Epic 11 on). It summarises the course brief *AI Capstone Project - AI Engineering* (Turing College) in our own words; the course text is not copied here. The owner keeps the full brief. When this summary and the full brief seem to differ, the full brief wins: ask the owner. The Sprint 2 and Sprint 3 briefs (`docs/BRIEF.md`, `docs/BRIEF_SPRINT3.md`) are read only when a ticket changes something they cover (the "Using this file" section below).

The Capstone builds on the Sprint 3 project (owner, 2026-11-19): the repository was cloned with its full history into https://github.com/NMH1988/fitkompass, and the app is renamed FitKompass (T11.2). What we decided to build is in `docs/PRD.md` ("Capstone: FitKompass", added by T11.1).

**Deadline:** 2026-12-16 (the owner's course schedule; the brief itself names no date).

## What the Capstone brief asks for

An open-ended project that applies what the course taught (LLM APIs, embeddings, retrieval-augmented generation, agents, prompt engineering, function calling, ethical AI) to a real-world problem, ideally as a deployed prototype, with tools such as LangChain, Streamlit and ChromaDB. The learner picks one of seven cases or proposes an own idea that meets the same requirements. The brief recommends taking part in the module's workshops and open sessions, and points to a course guide on choosing a distinctive problem and planning the time.

**README requirement (R):** the project folder has a `README.md` that says briefly what the project's goal is, which problem it solves and how it works; a link to the project's showcase entry is recommended near its top (E5).

### The seven cases (summary)

1. RAG knowledge assistant (data preparation, a vector database, a retrieval chain, a Streamlit UI, testing, an ethics note).
2. **AI agent for task automation** (chosen; steps below).
3. Smart document search over a large document set.
4. **Multimodal application** combining text and images (one tool chosen; steps below).
5. Coding assistant (generation, debugging, optimisation).
6. A deeper study of one or more advanced topics, with a written outcome.
7. LLM parameter tuning experiments with a dataset of results and a presentation.

### Case 2: AI agent for task automation (numbering ours, so tickets can cite it)

Goal: an agent that automates a complex workflow (the brief's examples: data analysis, reports, customer support). Suggested tools: LangChain, Python or JavaScript, function calling, external APIs. Outcome: a practical agent that shows LLM-powered automation.

1. **Agent design:** the agent's purpose and what it can do.
2. **Tool integration:** tools such as API calls, database queries or web scraping.
3. **Agent execution:** advanced features such as long-term memory, code execution or multi-step reasoning.
4. **Interactive prototype:** Streamlit or another interface for live use.
5. **Evaluation:** the agent's accuracy and responsiveness, assessed through user testing.
6. **Documentation:** a full report on what the agent does and on its ethical considerations.

### Case 4: Multimodal application (numbering ours)

Goal: an app that combines text and image processing. Suggested tools: an image model through OpenRouter, CLIP, Whisper, LangChain. Outcome: an app that combines text and image capabilities.

1. **Image and text analysis:** users upload images and get captions or extracted metadata.
2. **Cross-modal search:** find images or text from a user's query.
3. **Generative features:** images from descriptions, or the reverse.
4. **Interactive application:** a UI that brings the text and image functions together.

### Evaluation (the same for every case; numbering ours)

- **E1 Outcome quality:** (a) the project is complete and works; (b) the quality of the UI and the interaction, where there is one; (c) a clear description of the project's purpose and what it achieves, including the README paragraph (R).
- **E2 Learning application:** (a) effective use of tools such as LangChain, ChromaDB or LLM APIs; (b) best practices in prompt engineering and application design.
- **E3 Ethical considerations:** awareness of the ethical and privacy issues of building AI applications.
- **E4 Presentation:** a clear explanation of the project's purpose, how it is built and its impact, structured with SCR (situation, complication, resolution) or SMART (specific, measurable, achievable, relevant, time-bound).
- **E5 Showcase (optional, a small part of the score):** the project uploaded to showcase.turingcollege.com before the review is booked, its link near the top of the README, and the entry kept up to date when the project changes (also after a resit).

### Presentation (optional, strongly recommended; numbering ours)

Ten minutes and five minutes of questions, for example at a morning standup, around six points:

1. **The problem:** what it solves, for whom, and why it matters.
2. **The solution:** what was built: the architecture, the models and the key tools.
3. **The data:** what data was used and how it was prepared or handled.
4. **Evaluation:** how success was measured, with the metrics and results.
5. **Challenges:** the hardest technical problem and how it was solved.
6. **What's next:** what to improve or build with more time.

## The case we chose, and why

**Case 2, with one Case 4 tool** (owner's decision, 2026-11-19). FitKompass is a coaching workspace where a coach and a gymer talk in real time and an agent works on that conversation: it drafts log entries from the gymer's messages, summaries and reply drafts for the coach, and dishes that fit the coach's meal plan, each a proposal a person approves (Case 2 steps 1-4). Sprint 3 already gives it tools (the knowledge base, the USDA data and API, the store's reads), long-term memory and multi-step reasoning with human-in-the-loop pauses, so the Capstone adds the workflow a coach does by hand today: reading messages and turning them into logged data, plans and replies. The Case 4 tool (P1) turns a photo or a voice note into a draft log entry the gymer approves (Case 4 step 1). The other Case 4 steps (cross-modal search, image generation) are not planned.

Why not the others: Case 1 and Case 3 are mostly what Sprint 2 built (advanced RAG over a CC BY knowledge base); Cases 5-7 leave the product behind. Case 2 lets the existing users (coaches and gymers) and data carry over, and its user testing and report (steps 5 and 6) fit the evaluation (E1-E4).

## Using this file

- At the start of every ticket, name the Capstone items it serves by the numbers above (Case 2 step n, Case 4 step n, E n with its letter, R, or presentation point n), or "none"; write "beyond the brief (owner's request)" only when no brief covers the work. Name a Sprint 3 item (`docs/BRIEF_SPRINT3.md`) or a Sprint 2 item (`docs/BRIEF.md`) only when the ticket changes something one of them covers (for example a Sprint 3 review point still open, such as T10.10); otherwise write "none" for each. The PR description's Brief section, the plan's **Serves** line and the PROGRESS **Brief:** line carry the same numbers.
- If a ticket contradicts this brief, the PRD or the copyright policy, or changes what the product does, say so and ask the owner.
