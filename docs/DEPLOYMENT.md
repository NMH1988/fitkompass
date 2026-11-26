# Deployment notes

Not deployed yet. For the course review the app runs locally. This file collects what must be true before a public deployment, so the first deploy is not done from memory. Check the hosting provider's current documentation at deploy time; the details below were not re-checked against it.

## Target

**Streamlit Community Cloud** (free, deploys straight from this GitHub repo, redeploys on every push to `main`). Alternatives if it does not fit: Hugging Face Spaces, Render.

## Rule zero: nobody spends the owner's OpenRouter key

The owner's key must never be usable by an anonymous visitor. The key also stops working after the course, so the public demo must not depend on it. Choose one option before deploying:

1. **Bring your own key (recommended for the portfolio demo).** The visitor pastes their own OpenRouter key into a password field. It is kept only for that browser session, never logged, stored, or shown, and the app explains this. The owner's key is not configured on the server at all.
2. **Access gate plus spending limit.** Only invited people can open the app (private app or a password check), the owner's key is stored in the host's secrets settings, and the key has a credit limit set in OpenRouter's key settings, plus the in-app per-session rate limit.

Either way:
- The key is never in the repo, in logs, in error messages or in the page.
- When the key is missing, invalid or out of credit (401/402), the app shows a clear message instead of crashing.
- GitHub secret scanning and push protection are on for the repo (Settings -> Code security), so an accidentally committed key is blocked or reported.
- If a key ever leaks: revoke it on https://openrouter.ai/keys first, then clean up.
- The optional USDA FoodData Central API key (`USDA_FDC_API_KEY`, T9.9) follows the same rules. It costs nothing, but visitors share its quota (1,000 requests an hour; USDA blocks the key for an hour beyond that), and USDA deactivates a key found in public: set it only behind the access gate (option 2), or leave it unset so the food lookup uses the local table only.

## Checklist before the first deploy

1. **Runs from a clean clone.** Follow the README on a fresh checkout: install, download sources, build the index, run. Fix anything that needs a file that is not in the repo.
2. **Dependencies.** Runtime packages pinned in `pyproject.toml`. Check which dependency file and Python version the host reads, and set the Python version in the host's settings to match `.python-version`.
3. **Secrets.** Only through the host's secrets settings (TOML, same names as `.streamlit/secrets.toml.example`). Never commit `.streamlit/secrets.toml`.
4. **Knowledge base on an ephemeral disk.** The host's disk is reset on restart. Decide in `docs/ARCHITECTURE.md` whether the Chroma index is rebuilt at startup (embedding cost on every cold start) or a built index is committed (allowed only under the copyright policy: approved CC BY sources, attribution in place).
5. **USDA data.** A trimmed copy of the Foundation Foods CSV (CC0) is committed as `data/usda_foods.csv` (T4.3), so a deploy needs no download.
6. **Limits.** Check the host's memory and CPU limits against Chroma, the embeddings and the PDF builder.
7. **Personal data.** A guest's profile and every chat stay in the session only; a signed-in user's data is in the local store (`data/store/`), which an ephemeral disk loses on restart and which is not encrypted; logs contain no profile values or chat text. Demo mode stays off, and so does LangSmith tracing unless the owner decided otherwise (section "Tracing with LangSmith").
8. **Costs.** Default model `openai/gpt-5-mini`, `max_tokens` capped, rate limit on; the token and cost display works.
9. **Legal text on the page.** The "not medical advice" disclaimer and a link to the sources and attribution are visible.
10. **Server address.** `.streamlit/config.toml` sets `server.address = "localhost"` (T1.7), so a local run is reachable from this machine only. A host may need another address (e.g. `0.0.0.0` in a container); change it only together with option 1 or 2 above, never on its own. Keep `browser.gatherUsageStats = false` and `client.showErrorDetails = "none"`.
11. **Compliance review.** The `compliance-reviewer` agent has run on the whole repo on `main` with no open Blocker or High finding and no open finding about personal data reaching a third party (such as the LangSmith one in `docs/SECURITY.md` "Compliance reviews"). A privacy notice, explicit consent for health data and a GDPR review with a DPIA are in place first (`docs/PRD.md` "The privacy change", and the Capstone's "Before any real user" list in its section "Capstone: FitKompass"); the owner, or a lawyer, decides how. The other items of the agent's "Before a public deployment" checklist (e.g. processors and transfers, controller roles with coaches, export and delete against GDPR Art. 15, 17 and 20, records, breach handling, encryption of the store) are done or decided by the owner (`.claude/rules/workflow.md`, T1.10).

## Model providers' terms (checked 2026-11-26, T11.10)

The app's use of OpenAI models through OpenRouter (the chat, the drafts, and since T11.10 photos and voice notes; `docs/ARCHITECTURE.md`, D29) was checked against the pages in force on 2026-11-26: OpenAI's Usage Policies (effective 2026-11-20), Services Agreement (effective 2026-01-01) and Service Terms (updated 2026-11-13), and OpenRouter's Terms and Privacy Policy (updated 2026-08-31). No conflict was found for the free, local course project. Every AI draft and weekly review is approved by a person (OpenAI's rule on high-stakes automation in medical areas). The chat's answers are not approved by a person; they are general information from cited sources, under the domain guardrails, the check that replaces a written training program (T10.5) and the disclaimer, and in a deployment with sign-in only coaches have the chat (a guest's chat with a session-only profile exists only in a clone with no sign-in, `docs/PRD.md` "Users and roles"). The guardrails refuse diagnosis, medical diets, injuries and intakes below the calorie floor (disordered eating, Service Terms section 9). Users who keep a profile are adults by their own declaration (the profile's age check; Services Agreement 3.3(c)); a guest chats without declaring an age, and a minor is refused only when the question says so. The photo instruction tells the model never to identify or describe people, which a prompt cannot guarantee (Service Terms section 6). consent (c) covers photos and voice notes (Services Agreement 3.2; OpenRouter's notice and consent duty); and no raw model access is offered (OpenRouter Terms 7(4), OpenAI's intermediary rule). This is a reading of the pages, not legal advice. The point to keep watching is OpenAI's ban on "tailored advice that requires a license" without a licensed professional: the AI must not give a gymer an individual plan that no coach has approved, and a guest's personal energy and macro targets in a clone with no sign-in are a calculation from published formulas, not a plan.

Before a public deployment, free or not, these come on top of the checklist above (item 11):
- **Which terms govern a routed request.** The app's contract is with OpenRouter only; OpenRouter is OpenAI's customer, and OpenRouter's provider list links OpenAI's consumer terms (D29). Read the model terms OpenRouter lists, and OpenRouter's data processing agreement (its Terms, section 10.2).
- **Retention.** The pinned OpenAI endpoints are not zero-data-retention (D29). Choose one: OpenRouter's `data_collection: "deny"` (one synthetic call first, and a change to the one pass-through rule in `.claude/rules/security-privacy.md`), zero data retention through Azure (gpt-5-mini only, so consents (a) and (c) would name Microsoft Azure; gpt-audio-mini has none), EU in-region routing (OpenRouter's provider routing page, read on 2026-11-26, offers it on its Business and Enterprise plans), or a data processing agreement on the owner's own account. D29 and the T11.10 known limit in `docs/SECURITY.md` list the same options.
- **The privacy notice** names OpenRouter and OpenAI, their retention and the image screening for abuse material, and that a photo or recording can hold other people, whom the gymer must keep out.

## Before charging users (owner's request, 2026-11-26)

Beyond the brief (owner's request): the course project is free and non-commercial. If the owner later charges coaches, these come on top of everything above. It is not a complete list: a lawyer checks the commercial and consumer duties of a paid service (contract and consumer information, tax and the like), which this file does not cover.
1. **An account of the owner's own.** Not the course's key: an OpenRouter account in the owner's name (its holder must be 18 or older) with OpenRouter's data processing agreement, or a direct contract with OpenAI (Services Agreement and its data processing addendum), which gives the clearest chain of terms.
2. **Terms of use for the app's users** that pass OpenAI's Usage Policies on to them (OpenRouter Terms 5.1 and 5.2 make the owner responsible for users' compliance), with the privacy notice above.
3. **Liability (a risk to plan for, not a breach).** Under a direct contract with OpenAI, the customer indemnifies OpenAI against third parties' claims about the app (Services Agreement 13.2), and OpenAI's own liability to the customer is capped at what the customer paid in the last twelve months (14.2). Through OpenRouter, OpenRouter's Terms set the equivalent between the owner and OpenRouter (their later sections, read in full before launch). Paying users can claim more from the owner than a free demo's visitors, while the providers' liability to the owner stays small; consider professional liability insurance.
4. **The medical boundary.** Keep general information with a person approving every draft. Individual advice needs a licensed professional (OpenAI's Usage Policies) and a check of the German rules; a lawyer checks the EU AI Act's transparency duties (Art. 50) and the medical-device boundary for the paid product.
5. **Data.** The retention choice above, a DPIA and a transfer basis for the US providers (the EU-US Data Privacy Framework or standard contractual clauses) are already required by item 11 for any public deployment with real users; a paid version keeps them current as the product grows.
6. **No raw model access.** The subscription buys the app's features; reselling API access is barred (OpenRouter Terms 7(4); OpenAI's intermediary rule).
7. **Age.** A stronger check than the self-declared adult age.
8. **Licences.** No change needed: the knowledge base (CC BY), the USDA data (CC0), the DejaVu fonts embedded in the PDF summary (`assets/fonts/LICENSE`), the README's screenshots of the app's own synthetic data, and the runtime dependencies (MIT, BSD, Apache-2.0 and the like, `tests/test_dependency_licences.py`) already allow commercial use; tools with copyleft licences (Piper, FFmpeg) run only on the owner's machine (`docs/SOURCES.md`).
9. **An Impressum.** A commercial digital service must keep the provider's name, address and e-mail contact easy to find and always reachable (DDG section 5, read on gesetze-im-internet.de on 2026-11-26).
10. **Watch the terms.** OpenAI and OpenRouter give about 30 days' notice of material changes; check these pages again before launch.

## Sign-in with Google on localhost (T9.5)

Optional: without it the app runs for guests (and, with `DEMO_MODE`, in demo mode). The owner sets it up (O9); Claude never creates the Google client or enters credentials.

1. In the Google Cloud console, create a project (free), then the **OAuth consent screen** (newer consoles call it Google Auth Platform, with Branding and Audience pages; the wording below may differ): user type External, publishing status **Testing**, scopes `openid`, `email` and `profile` only. Under **Test users**, add the Google accounts that will play the coach and the gymers: in Testing mode only they can sign in.
2. **Credentials -> Create credentials -> OAuth client ID**, application type **Web application**, authorised redirect URI `http://localhost:8501/oauth2callback` (the app's port; `server.address = "localhost"` keeps it on this machine).
3. In `.streamlit/secrets.toml` (gitignored), uncomment the `[auth]` and `[account]` sections copied from `.streamlit/secrets.toml.example` and fill them: the client ID and secret, a random `cookie_secret` and a random `user_key_secret`, each of at least 32 characters (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`, run once for each). The app offers sign-in only when neither secret is the example's placeholder or shorter than 32 characters (a placeholder client ID or secret shows the button, which then fails at Google). Keep `user_key_secret` once set: a new one gives every user a new, empty account.
4. Restart the app. It opens on the start page with only "Sign in with Google" (no guest once sign-in is set up; owner's choice, 2026-11-02); at the first sign-in the user chooses Coach or Gymer (once) and a display name. If the sidebar says sign-in is off, the app found no `[auth]` section; if it says `secrets.toml` could not be read, the file has a TOML syntax error.

What is stored and who sees it: `docs/PRD.md` "The privacy change" and `docs/SECURITY.md`. Use made-up data only; screenshots of a signed-in page use demo mode or a test account, with the Google name, e-mail address and picture out of the picture (the app shows none of them itself).

**A public deployment** needs its own redirect URI (the deployed URL with `/oauth2callback`) in both the Google client and the host's secrets, the consent screen published (Google's verification), and everything in the checklist above; Streamlit turns CORS and XSRF protection on when `[auth]` is set.

## Demo mode (T9.5, D18)

For a reviewer or a clone with no Google client: set `DEMO_MODE = true` in `.streamlit/secrets.toml` (or the environment variable `DEMO_MODE=1`) and leave the `[auth]` section out (with `[auth]` demo mode is ignored). The start page offers a "Demo user" picker (no guest) with five made-up users (`src/demo.py`: a coach, a gymer who shares body and nutrition with that coach, a gymer with no coach and, from T11.8, two more clients of the coach who share nutrition and rated one of the coach's recipes), on a temporary database seeded when the app starts and deleted when it stops; `data/store/` is not touched. Never turn demo mode on for a deployment that real people use: anyone at the browser can pick any demo user.

## Tracing with LangSmith (T9.8, D19)

Off unless `FITKOMPASS_TRACING` and `LANGSMITH_API_KEY` are both set (secrets or environment); LangSmith's own `LANGSMITH_TRACING` flag is ignored. The account is in the EU region (`config.LANGSMITH_ENDPOINT`; the owner creates it, O10). A trace holds metadata only, except in T9.35's demo mode below (`docs/SECURITY.md`, the LangSmith row). A public deployment leaves both unset until the owner has decided on LangSmith as a processor (a data processing agreement, the transfer to a US company even with EU storage) and the privacy notice names it.

`FITKOMPASS_TRACING_DEMO_UNMASKED` (T9.35) is for a local demo with made-up users only: it works only with `DEMO_MODE` and never with `[auth]`, and a public deployment never sets it.

## Real-time messages (T11.4b, D24)

The chat socket is mounted on Streamlit's own server: `streamlit run serve.py` serves the pages and the socket (at `/realtime/ws`) from one process and one port; `streamlit run app.py` serves the pages alone, and the Messages page is then read-only. Locally the socket accepts only a page at `http://localhost:<port>` or `http://127.0.0.1:<port>` on the port Streamlit serves. Before a public deployment of the socket (compliance run 1 of T11.4a): the page and the socket over https and `wss://` (TLS at the host or a reverse proxy that passes WebSocket upgrades on `/realtime/ws`), the public https origin added to `config.CHAT_PUBLIC_ORIGINS`, the access gate of option 2, the token secret (`[chat] token_secret`) in the host's secret settings, a send rate limit, a store on a disk that survives restarts, a proxy's or host's own access lines (address, path, time) in the privacy notice and the retention plan, and the real-time design passed to the lawyer's TDDDG §3 review (`docs/PRD.md`, "Before any real user"). On Streamlit's server the socket has Streamlit's own uvicorn settings, not the stricter ones T11.4a's separate server had: a frame up to `server.maxMessageSize` (200 MB by default) is read before the socket's own 8 KB cap closes it, and the proxy and server headers are uvicorn's defaults as Streamlit sets them; decide for the deployment whether to lower `server.maxMessageSize` (it caps Streamlit's own messages too, such as uploads) and which proxy may set forwarded headers. Whether Streamlit Community Cloud runs an `st.App` main file and passes a custom WebSocket path is not documented (checked 2026-11-23); a host that runs `streamlit run serve.py` behind TLS does.

## Deploy steps (Streamlit Community Cloud, first time)

1. Sign in at https://share.streamlit.io with the GitHub account that owns the repo.
2. Create an app: repo `NMH1988/fitkompass`, branch `main`, main file `app.py` (`serve.py` for real-time messages, once the items in "Real-time messages" above are done).
3. In advanced settings: choose the Python version; paste secrets only if option 2 above is used.
4. Deploy, open the URL, and run the checks below.
5. Optional: set the repo variable `APP_URL` and add the Sprint 1 style CD workflow that waits for CI on `main` and then calls `<APP_URL>/_stcore/health`.

## Copying the repo to the course repository

The work happens in `NMH1988/fitkompass` (since 2026-11-19, the Capstone; before that in `NMH1988/fitcoach-ai-assistant` from 2026-10-26, and it started in `NMH1988/nutrition-ai-assistant`, where the earlier `#<n>` numbers live); when it is finished, it is copied into the repository the course provides, where the reviewers read it. Only files and commit history travel; issues, pull requests, PR descriptions and review comments stay behind.

Before copying:
1. `docs/IMPLEMENTATION_PLAN.md` (the order table) and `docs/tickets/` show every ticket's final status, and `docs/PROGRESS.md` lists an entry (a file in `docs/progress/`) for every merged PR.
2. The README explains how to install, download the sources, build the index and run the app, and links the docs.
3. CI is green on `main`; no secrets in the history (GitHub secret scanning shows no alerts).
4. Docs refer to tickets by ID (`T1.2`). The `#<n>` issue and PR numbers stay as they are: the README, `docs/IMPLEMENTATION_PLAN.md` and `docs/PROGRESS.md` say they refer to the personal repo, and that a source number is a row in `docs/SOURCES.md` (owner's choice in T6.2, 2026-10-22, instead of rewriting about 400 numbers as full URLs).
5. The `compliance-reviewer` agent has run on the whole repo on `main` with no open Blocker or High finding (`.claude/rules/workflow.md`, T1.10).

Copying (keeps the full history):
1. Clone the course repository and check that it is empty, or note what the course put there (e.g. its own README) so nothing of theirs is overwritten without asking.
2. From the personal repo: `git remote add course <course repo URL>` and `git push course main` (add `--force` only if the course repo is empty apart from a placeholder and the course allows it). If the course repo already has commits of its own, merge instead, as in "Updating the course repository later" below; the first merge into a new course repo needs `--allow-unrelated-histories` (the two histories share no commit), the later updates do not.
3. In the course repo: check that the README renders and CI runs. If the reviewers work through pull requests, disable or delete `.github/workflows/pr-checks.yml` there: it fails any PR that does not close an issue, and the course repo may have no issues. `.github/workflows/eval.yml` (T8.6) comes along too: it runs only when someone with write access starts it, and the course repository has no `OPENROUTER_API_KEY_EVAL` secret (never add one there), so a started run stops at the index build with the missing-key message and spends nothing.
4. Update the repo links in `docs/BRIEF.md` and this file if the reviewers should only see the course repo. The links to the personal repo in the `#<n>` notes of `README.md`, `docs/IMPLEMENTATION_PLAN.md` and `docs/PROGRESS.md` stay: the numbers only make sense there.

Done on 2026-10-22 (T6.2): the course repository is https://github.com/TuringCollegeSubmissions/mnguye-AE.AFA.updated0209.2.5. It held the course's first commit with its task description (`125.md`), which is kept, so the copy is a merge of that commit (fc25447) and this repo's `main` at 8bcdc74, not a force push; the course repo's `main` is then 8a27496. The reviewers read the files only (O6), so `pr-checks.yml` stays.

Done on 2026-11-16 (T9.11b, Sprint 3): the course repository is https://github.com/TuringCollegeSubmissions/mnguye-AE.AFA.updated0209.3.6 (private, the course's). It held the course's first commit with its task description (`135.md`), which is kept, so the copy is again a merge, of that commit (0c3c9ed) and this repo's `main` at 8b53c17, after the whole-repo compliance run on 8b53c17 (`docs/SECURITY.md`, "Compliance reviews"); the course repo's `main` is then 1ee22dd, which differs from 8b53c17 only by `135.md`, and CI passed on it (lint, test, security). The README renders. As for Sprint 2, the reviewers are taken to read the files only, so `pr-checks.yml` stays. Dependabot's configuration travels with the files, so Dependabot opened five bump PRs in the course repository too; the owner had them closed unmerged (bumps reach it through this repo's `main`), and, as GitHub has no switch for version updates and the owner has write access there, not admin, a commit in the course repository only (3b7fb33, 2026-11-16) removed `.github/dependabot.yml` there; this repo keeps it. Since then, right after each update, the course repo's `main` differs from this repo's `main` by `135.md` and the missing `.github/dependabot.yml`. Later updates follow the steps below.

Updating the course repository later (allowed before the deadline):
1. Merge the change into this repo's `main` first, through its PR as usual.
2. The `compliance-reviewer` agent has run on the whole repo on `origin/main` after that merge, so it checks what step 3 pushes, with no open Blocker or High finding (`.claude/rules/workflow.md`, T1.10); its licence listing also covers the Dependabot bumps merged since the last run.
3. Merge this repo's `main` into the course repo's `main` (it has its own merge commit, so a fast-forward is not possible and a plain `git push course main` is rejected), never with `--force`, and push it there:
   ```bash
   git fetch origin
   git fetch course
   git switch --detach course/main
   git merge origin/main -m "T<x.y> Update from NMH1988/fitkompass"
   # Sprint 3 only: if the merge stops on a modify/delete conflict for .github/dependabot.yml
   # (this repo changed the file the course repo removed), keep it removed, then go on:
   #   git rm .github/dependabot.yml
   #   git commit --no-edit
   git diff --stat origin/main HEAD    # must show only the course's task file (and, for Sprint 3, the removed .github/dependabot.yml)
   git log --oneline -1 HEAD^2    # must be the merged PR's commit on main
   git push course HEAD:main
   git switch main
   ```
   It merges `origin/main`, not the local `main`, which may not have the PR merged on GitHub yet. While this repo leaves `.github/dependabot.yml` unchanged, the merge keeps it removed in the course repo with no conflict.
   Never merge `course/main` into this repo's `main`: the course's own commit (its task file, `125.md` for Sprint 2, `135.md` for Sprint 3) would land in the personal repo.
4. Check that CI passes on the course repo's new `main`.

## After each deploy

- The app loads and answers one question with sources.
- Each tool runs once and its result shows.
- The PDF download works.
- The key does not appear in the page, the browser's network tab or the logs.
- A request without a valid key shows the friendly error.
