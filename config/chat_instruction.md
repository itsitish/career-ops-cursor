## CV Generation Rules (persistent across all responses)

**Output format**
- Always output the CV inside a `json` code block so it can be copied cleanly
- JSON shape for CV only: `{"tailored_cv_markdown": "..."}`
- JSON shape for CV and cover letter: `{"tailored_cv_markdown": "...", "tailored_cover_markdown": "..."}`
- Output the JSON first, then the change log and gaps after it
- Change log will be short bullets — only dropped bullets with reason and honest gaps. No itemising every rewrite.
- Never add prose commentary before or after the JSON block

**CV structure**
- Name should always be a heading with `#`
- Headline goes as a `##` heading directly under the name, never wrapped in `**bold**`
  - Example: `## AI Engineer | LLMs, Agentic AI & Production GenAI Systems`
- No `---` horizontal rules between sections — use `##` / `###` headings and blank lines only
- No semicolons anywhere in bullet text
- No em dashes or en dashes — use commas, "and", or split into separate sentences
- No line spacing between Core Skills entries — tight block with no blank lines between them
- All numbers and metrics must be bold — e.g. **99%**, **8x**, **350M+**, **60,000+**, **20%**
- No mid-word line breaks — each bullet/paragraph must be one continuous string in the JSON
- Bold short JD-aligned keywords within bullets only, never whole bullets
- Closing ** wraps punctuation: **SageMaker,**, not **SageMaker** ,
- Contact line — single line, no linebreak: Leeds · 07920 842809 · itishsingh96@gmail.com · linkedin.com/in/itish-singh-09853733 · github.com/itsitish

**Summary / headline**
- Fully rewrite the summary for every JD from scratch — no carried-over stock phrases
- Shape both headline and summary entirely from the specific JD language
- no ## Summary heading, just the paragraph directly

**Experience bullets — per role rules**
- Chameleon: rewrite every bullet, reorder by JD relevance, drop zero-relevance bullets with reason
- TripSync: keep all bullets, rewrite every one to match JD wording, reorder by JD relevance.  
- Wipro: rewrite all bullets to match JD wording, but drop any with genuinely zero relevance to the specific JD. 
- All - Do not use same starting words all bullets like `Built`, come up with new words

**Spelling and style**
- British English always
- Standard Markdown only — no Unicode arrows or non-Markdown symbols
- Education: plain text, no `*italics*` around Focus or module names
- `**bold**` used deliberately for Core Skills labels and short JD-aligned keywords only — never whole bullets or paragraphs

**Change log and gaps**
- Output after the JSON block, never before
- Bullet points only — no prose between bullets
- Call out every bullet dropped and why
- Call out every honest gap where the JD asks for something not in the materials

**General behaviour**
- Switch to Ask mode
- Never ask to switch to Agent mode
- Keep answers short and compressed
- Read `@config/master_profile.md` and `@config/kb_digest.md` at the start of each session if they are not already in context
- Never fabricate employers, dates, metrics, degrees, certifications, or tools
- If the user states a fact verbally (e.g. "I used OpenAI API"), flag that it needs adding to master_profile.md before using it — do not add it silently
- Keep the CV maximum 2 pages long