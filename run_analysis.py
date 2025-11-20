# run_analysis.py (OpenAI-only clean version)

import os
import re
import json
import traceback
from datetime import datetime
from analyzer.impact_analyzer import analyze

# ---------------------------------------------
# OpenAI Client (New API format)
# ---------------------------------------------
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    openai_client = None


# ---------------------------------------------
# Utility Functions
# ---------------------------------------------
def load_changed_files():
    raw = os.getenv("CHANGED_FILES", "").strip()
    if not raw:
        return []
    return [line.strip() for line in raw.split("\n") if line.strip()]


def safe_output(txt):
    """Ensure non-empty output to avoid GitHub 422 comment errors."""
    if not txt or not txt.strip():
        return (
            "# Impact Analysis Report\n"
            "⚠️ AI engine returned no content.\n"
            "This may occur when no relevant code changes were detected."
        )
    return txt


def read_file_content(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


# ---------------------------------------------
# Microservice Dependency Scanner
# ---------------------------------------------
def discover_microservices(base_dir):
    """
    Automatically collect source files for all detected microservices.
    A microservice is any top-level folder beginning with:
    ui-, crud-, domain-, fdr-, psg-, apigee-
    """
    services = {}
    prefixes = ("ui-", "crud-", "domain-", "fdr-", "psg-", "apigee-")

    for entry in os.listdir(base_dir):
        full_path = os.path.join(base_dir, entry)
        if os.path.isdir(full_path) and entry.startswith(prefixes):
            services[entry] = []
            for root, dirs, files in os.walk(full_path):
                for f in files:
                    if f.endswith((".py", ".ts", ".js", ".json", ".yml", ".yaml")):
                        services[entry].append(os.path.join(root, f))

    return services


def extract_dependencies(file_content):
    """
    A very lightweight static dependency extractor:
    - python imports
    - js/ts imports
    - http endpoints
    """
    deps = set()

    # Python imports
    for match in re.findall(r"from\s+([\w_\.]+)\s+import|import\s+([\w_\.]+)", file_content):
        for m in match:
            if m:
                deps.add(m.split(".")[0])

    # JS/TS import paths
    for match in re.findall(r"from ['\"]([^'\"]+)['\"]", file_content):
        # only consider internal paths (avoid packages)
        if "/" in match:
            deps.add(match.split("/")[0])

    # API endpoints
    for url in re.findall(r"https?://[^\"\']+", file_content):
        deps.add(url)

    return deps


def build_dependency_graph(services):
    """
    Build a graph:
    { service_name: { "files": [...], "deps": {other_service: count} } }
    """
    graph = {}

    for svc, files in services.items():
        graph[svc] = {"files": files, "deps": {}}

        for file_path in files:
            content = read_file_content(file_path)
            deps = extract_dependencies(content)

            for dep in deps:
                for target_svc in services:
                    if target_svc in dep and target_svc != svc:
                        graph[svc]["deps"].setdefault(target_svc, 0)
                        graph[svc]["deps"][target_svc] += 1

    return graph


# ---------------------------------------------
# OpenAI LLM Analysis
# ---------------------------------------------
def llm_analysis(pr_title, changed_files, graph):
    """
    Performs impact analysis using OpenAI.
    Falls back gracefully if API fails.
    """

    if not openai_client:
        return "⚠️ OpenAI client is not initialized. Missing OPENAI_API_KEY?"

    prompt = f"""
You are an intelligent impact analysis engine.

Analyze the following Pull Request context and produce a detailed
multi-service technical impact assessment.

----------------------------
PR Title:
{pr_title}

Changed Files:
{json.dumps(changed_files, indent=2)}

Service Dependency Graph:
{json.dumps(graph, indent=2)}
----------------------------

Your tasks:
1. Identify which microservices are directly impacted.
2. Identify indirect downstream impact via dependency edges.
3. Classify the overall risk as: LOW / MEDIUM / HIGH.
4. Provide recommended test cases.
5. Suggest fixes or refactoring if needed.
6. Output findings in clean GitHub Markdown.
"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
        )
        return response.choices[0].message.content

    except Exception as e:
        return f"⚠️ OpenAI LLM failed:\n```\n{str(e)}\n```"


# ---------------------------------------------
# Main Analysis
# ---------------------------------------------
def run_analysis():
    pr_title = os.getenv("PR_TITLE", "(no PR title)")
    base_dir = os.getenv("REPOS_BASE_DIR", ".")
    changed_files = load_changed_files()

    report = []
    report.append("# Impact Analysis Report")
    report.append(f"Generated: `{datetime.utcnow()} UTC`")
    report.append(f"**PR Title:** {pr_title}")
    report.append("")

    if not changed_files:
        report.append("### No changed files detected.")
        return "\n".join(report)

    report.append("### Changed Files")
    for c in changed_files:
        report.append(f"- `{c}`")
    report.append("")

    # Discover services + dependency graph
    services = discover_microservices(base_dir)
    graph = build_dependency_graph(services)

    report.append("### Microservice Dependency Summary")
    for svc, data in graph.items():
        deps = ", ".join(data["deps"].keys()) or "None"
        report.append(f"- **{svc}** → depends on: {deps}")
    report.append("")

    # AI section
    report.append("## AI Analysis")
    ai_output = analyze(pr_title, changed_files, graph)
    report.append(ai_output)

    return "\n".join(report)


# ---------------------------------------------
# Entrypoint
# ---------------------------------------------
if __name__ == "__main__":
    try:
        final = run_analysis()
        print(safe_output(final))
    except Exception as e:
        print("# Impact Analysis Error")
        print(str(e))
        print("```")
        print(traceback.format_exc())
        print("```")
