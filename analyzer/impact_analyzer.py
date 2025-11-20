import json
import os
import re

# OpenAI Client
try:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    client = None


def _shorten_path(path):
    return path.replace("\\", "/").split("/")[-1]


def build_llm_prompt(pr_title, changed_files, graph):
    """
    Generates a beautiful Markdown-based Impact Review.
    """

    return f"""
You are a senior software architect writing a beautifully structured, highly readable
GitHub Pull Request impact analysis comment.

Use MARKDOWN ONLY. GitHub must render it cleanly.

Generate a detailed report with the following structure:

================================================================================
# 🎛️ Impact Analysis Dashboard (Top Summary)
- Use a **Markdown table** summarizing:
  - Severity (LOW / MEDIUM / HIGH with emoji)
  - Impacted services
  - Count of changed files
  - High-level recommendation

================================================================================
# 📝 Summary of What Changed
- Explain PR Title impact in 3–5 sentences.
- Describe how the changed files influence upstream/downstream contracts.

================================================================================
# 🧩 Downstream Impact Breakdown

For EACH impacted service in the dependency graph:
## <service-name>
**Why impacted:** 1–2 sentences  
**Files to review:** List **actual files from the graph** (max 8)  
**Recommended fixes:** Bullet points  
**Risk:** LOW / MEDIUM / HIGH  

Keep sections well-structured with headings & bold labels.

================================================================================
# 🧪 Recommended Test Coverage
- List 4–7 test cases developers should run.

================================================================================
# 🧠 Final Reviewer Guidance
- Summarize in 3–6 sentences what the reviewer should consider before merging.
------------------------------------------------------------------------------

### INPUT DATA

PR Title:
{pr_title}

Changed Files:
{json.dumps(changed_files, indent=2)}

Dependency Graph:
{json.dumps(graph, indent=2)}

------------------------------------------------------------------------------

### OUTPUT FORMAT
MUST be pure Markdown — no JSON, no backticks around the entire output.
"""


def analyze(pr_title, changed_files, graph):
    if not client:
        return "⚠️ Missing OPENAI_API_KEY for analysis."

    prompt = build_llm_prompt(pr_title, changed_files, graph)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1900,
            temperature=0.2,
        )
        return response.choices[0].message.content

    except Exception as e:
        return f"⚠️ AI engine failed:\n```\n{str(e)}\n```"
