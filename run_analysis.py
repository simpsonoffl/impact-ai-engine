# run analysis stub
import os
import re
import traceback
import json
from datetime import datetime
from pathlib import Path

# Optional AI clients
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except:
    openai_client = None

try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except:
    pass


# ------------------------------------------------------
# Utility functions
# ------------------------------------------------------
def load_changed_files():
    raw = os.getenv("CHANGED_FILES", "").strip()
    if not raw:
        return []
    return [f.strip() for f in raw.replace(",", "\n").split("\n") if f.strip()]


def safe_output(txt):
    """Guarantee non-empty output"""
    if not txt or not txt.strip():
        return (
            "# Impact Analysis Report\n"
            "The analysis engine returned no data.\n"
            "This may happen when no changes or no analyzable code exists.\n"
        )
    return txt


def read_file_content(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except:
        return ""


# ------------------------------------------------------
# Microservice Dependency Scanner
# ------------------------------------------------------
def discover_microservices(base_dir):
    """
    Returns a dict of service → file list
    Example:
    { "ui-account-load": ["src/app/..."], "crud-ms-account-load-db": [...] }
    """
    services = {}
    for entry in os.listdir(base_dir):
        full = os.path.join(base_dir, entry)
        if os.path.isdir(full) and entry.startswith(("ui-", "crud-", "domain-", "fdr-", "psg-", "apigee-")):
            services[entry] = []
            for root, dirs, files in os.walk(full):
                for f in files:
                    if f.endswith((".py", ".ts", ".js", ".json", ".yml", ".yaml")):
                        services[entry].append(os.path.join(root, f))
    return services


def extract_dependencies(file_content):
    """
    Very simple dependency heuristics:
    - import statements
    - URL references (API calls)
    - Shared models/modules
    """
    deps = set()

    # Python imports
    for match in re.findall(r"from\s+([\w_\.]+)\s+import|import\s+([\w_\.]+)", file_content):
        for m in match:
            if m:
                deps.add(m.split(".")[0])

    # TS/JS imports
    for match in re.findall(r"from ['\"]([^'\"]+)['\"]", file_content):
        if "/" in match:
            deps.add(match.split("/")[0])

    # API endpoints
    for match in re.findall(r"https?://[^\"']+", file_content):
        deps.add(match)

    return deps


def build_dependency_graph(services):
    """
    Returns: { service_name: { "file": [...], "deps": {service: count}} }
    """
    graph = {}

    for service, files in services.items():
        graph[service] = {"files": files, "deps": {}}

        for f in files:
            content = read_file_content(f)
            deps = extract_dependencies(content)

            for dep in deps:
                for svc in services:
                    if svc in dep and svc != service:
                        graph[service]["deps"].setdefault(svc, 0)
                        graph[service]["deps"][svc] += 1

    return graph


# ------------------------------------------------------
# AI Engine
# ------------------------------------------------------
def llm_analysis(pr_title, changed, graph):
    """
    Combines OpenAI + Gemini fallback
    """
    prompt = f"""
You are an impact analysis engine. Analyze the PR:

Title: {pr_title}

Changed Files:
{json.dumps(changed, indent=2)}

Service Dependency Graph:
{json.dumps(graph, indent=2)}

TASKS:
1. Identify which microservices are directly impacted.
2. Identify downstream indirect impact via dependency edges.
3. Classify overall risk as LOW / MEDIUM / HIGH.
4. Provide recommended testing steps.
5. Provide recommended fixes or refactoring.
6. Format the result in GitHub Markdown.
    """

    # Try OpenAI first
    if openai_client:
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4.1",
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content
        except Exception as e:
            pass

    # Fallback to Gemini
    try:
        gemini = genai.GenerativeModel("gemini-1.5-pro")
        out = gemini.generate_content(prompt)
        return out.text
    except:
        return "AI processing failed (OpenAI + Gemini both failed)."


# ------------------------------------------------------
# Main Analysis
# ------------------------------------------------------
def run_analysis():
    pr_title = os.getenv("PR_TITLE", "(no PR title)")
    base_dir = os.getenv("REPOS_BASE_DIR", ".")
    changed = load_changed_files()

    report = []
    report.append("# Impact Analysis Report")
    report.append(f"Generated: `{datetime.utcnow()} UTC`")
    report.append(f"**PR Title:** {pr_title}")
    report.append("")

    if not changed:
        report.append("### No changed files found.")
        return "\n".join(report)

    report.append("### Changed Files")
    for c in changed:
        report.append(f"- `{c}`")
    report.append("")

    # ----------------------------------------
    # Discover microservices + build graph
    # ----------------------------------------
    services = discover_microservices(base_dir)
    graph = build_dependency_graph(services)

    report.append("### Microservice Dependency Summary")
    for svc, data in graph.items():
        deps = ", ".join(data["deps"].keys()) or "None"
        report.append(f"- **{svc}** → depends on: {deps}")
    report.append("")

    # ----------------------------------------
    # LLM Analysis
    # ----------------------------------------
    report.append("## AI Analysis")
    try:
        ai_output = llm_analysis(pr_title, changed, graph)
        report.append(ai_output)
    except Exception as e:
        report.append("### ⚠ Error in AI Processing")
        report.append(str(e))
        report.append("```")
        report.append(traceback.format_exc())
        report.append("```")

    return "\n".join(report)


# ------------------------------------------------------
# Entry point (always safe)
# ------------------------------------------------------
if __name__ == "__main__":
    try:
        out = run_analysis()
        print(safe_output(out))
    except Exception as e:
        print("# Impact Analysis Error")
        print(str(e))
        print("```")
        print(traceback.format_exc())
        print("```")
