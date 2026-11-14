"""How the site takes the shared package (wts-core): the wheel of a tagged release, with the extras it uses and no
others; CI's shared workflows at the same tag; only what the package makes public; and no copy left behind of
anything the package now does."""

import ast
import importlib
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    [wts_core] = [d for d in project["dependencies"] if canonical(d.split("[")[0].split("@")[0].strip()) == "wts-core"]
    return wts_core


def test_the_shared_package_is_the_wheel_of_a_release_with_the_extras_the_site_uses():
    name, address = (part.strip() for part in requirement().split("@", 1))
    # Typer for the shared commands, httpx for off-site copies, and the model's SDK, the embedder and the index.
    # Not "duckdb": the site reads its own store with DuckDB, which is a dependency of its own.
    assert name == "wts-core[cli,offsite,ai]"
    # the wheel of a tagged release, by its address: the Docker image has no git (wts-core docs/adr/0006)
    assert re.fullmatch(r"https://github\.com/rj-mitchell/wts-core/releases/download/v(\d+\.\d+\.\d+)/"
                        r"wts_core-\1-py3-none-any\.whl", address)
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = {canonical(p["name"]): p for p in lock["package"]}
    [ours] = [d for d in locked["councils"]["dependencies"] if d["name"] == "wts-core"]
    assert sorted(ours["extra"]) == ["ai", "cli", "offsite"]
    assert locked["wts-core"]["source"]["url"] == address
    # the libraries the package's "ai" extra brings are no longer the site's own to name, nor an extra of its own
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    named = {canonical(re.split(r"[\[<>=@ ]", d, maxsplit=1)[0]) for d in project["dependencies"]}
    assert not {"anthropic", "lancedb", "fastembed"} & named
    assert "embed" not in project.get("optional-dependencies", {})
    for file in ("Dockerfile", "README.md", "docs/DEPLOY.md", "docs/OPERATIONS.md", ".github/workflows/ci.yml"):
        assert "--extra embed" not in (ROOT / file).read_text(), file


def test_ci_calls_the_shared_workflows_at_the_tag_of_the_package_installed():
    """One number to raise: the release of wts-core in pyproject.toml is the tag every shared workflow and action
    is called at in .github/workflows/ci.yml (wts-core docs/adr/0010), and Dependabot leaves them to be raised
    together by hand."""
    version = re.search(r"/download/(v[\d.]+)/", requirement())[1]
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    called = re.findall(r"uses: rj-mitchell/wts-core/(\S+)@(\S+)", ci)
    assert sorted(what for what, _ in called) == [
        ".github/actions/a11y", ".github/actions/setup", ".github/workflows/docker.yml",
        ".github/workflows/python.yml", ".github/workflows/web.yml"]
    assert {tag for _, tag in called} == {version}
    assert '- dependency-name: "rj-mitchell/wts-core*"' in (ROOT / ".github" / "dependabot.yml").read_text()


def test_ci_still_makes_every_check_it_made():
    """What each job did before the shared workflows, it does now (the shared workflows' own steps are read from
    the release the site installs, when a copy of the package's repository is beside this one; the names here
    are the checks this site's CI has always made)."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    for kept in ("workflows/python.yml@",                     # uv sync --frozen, ruff check, pytest
                 "workflows/web.yml@", "working-directory: web",      # npm ci, npm test, npm run build
                 "uv sync --frozen --python 3.12", "npm ci && npm run build",
                 "scripts/fixture_site.py", "councils serve --port 8000",
                 'grep -q "Members by party"', 'grep -q "Constituent councils"',
                 'grep -q "/votes/E08000038:1:10:0"',
                 "actions/a11y@", "url: http://127.0.0.1:8000", 'cat "$RUNNER_TEMP/serve.log"'):
        assert kept in ci, kept
    assert "pull_request:" in ci and "branches: [main]" in ci and "contents: read" in ci


def test_the_site_uses_only_what_the_shared_package_makes_public():
    """Everything the site (and its tests) takes from wts-core is in the ``__all__`` of the module it comes from:
    the package may change anything else without notice (wts-core docs/adr/0007)."""

    def public(module: str, name: str) -> bool:
        try:
            importlib.import_module(f"{module}.{name}")          # a module of the package
            return True
        except ImportError:
            return name in importlib.import_module(module).__all__

    checked = 0
    files = [*sorted((ROOT / "src").rglob("*.py")), *sorted((ROOT / "tests").rglob("*.py")),
             *sorted((ROOT / "scripts").rglob("*.py"))]
    for path in files:
        tree = ast.parse(path.read_text())
        modules: dict[str, str] = {}                                 # a name in this file -> the module it stands for
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "wts_core":
                assert not any(part.startswith("_") for part in node.module.split(".")), f"{path.name}: {node.module}"
                for alias in node.names:
                    assert public(node.module, alias.name), f"{path.name}: {node.module}.{alias.name} is private"
                    checked += 1
                    try:
                        importlib.import_module(f"{node.module}.{alias.name}")
                        modules[alias.asname or alias.name] = f"{node.module}.{alias.name}"
                    except ImportError:
                        pass
            elif isinstance(node, ast.Import):
                assert not any(a.name.split(".")[0] == "wts_core" for a in node.names), f"{path.name}: import wts_core"
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in modules \
                    and not _shadowed(tree, node.value.id):
                assert public(modules[node.value.id], node.attr), f"{path.name}: {modules[node.value.id]}.{node.attr}"
                checked += 1
    assert checked > 150


def _shadowed(tree, name: str) -> bool:
    """Whether a file also gives the name to something of its own (a variable called ``replies``, say)."""
    return any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store) for n in ast.walk(tree)) \
        or any(isinstance(n, ast.arg) and n.arg == name for n in ast.walk(tree))


# What the package does now, by the names the site's own copies had (every function and class of the modules that
# went, and those that went from the modules partly replaced). None is defined in the site any more; a name may
# still be used, where it is the package's, imported. Three names in the old modules are not here, because the
# site still has something of its own by that name: `get_embedder` (which of the package's embedders the settings
# ask for), and `check` and `_norm` (in sources/robots.py and sources/documents.py, which were never copies).
REPLACED_MODULES = ("rag/verify.py", "rag/neutral.py", "rag/british.py", "api/state.py", "api/usage.py",
                    "api/statements.py", "backup.py", "offsite.py", "embed/__init__.py", "embed/base.py")
REPLACED_NAMES = (
    # api/state.py, api/usage.py, api/statements.py
    "utcnow", "today", "months_before", "StateDB", "prices_for", "token_counts", "cost_usd", "network_of",
    "visitor_key", "record_usage", "spent", "count_question", "questions_today", "blocked", "site_paused",
    "InFlight", "RateLimiter", "word_count", "item_address", "check_text", "check_line", "check_link", "safe_link",
    "check_email",
    # backup.py, offsite.py
    "make_backup", "OffsiteError", "configured", "B2", "send", "backup_alerts",
    # rag/verify.py, rag/neutral.py, rag/british.py
    "Segment", "Verification", "recheck_flags", "drop_preambles", "verify", "check_quotes", "still_loaded",
    "flag_loaded", "outside_quotes", "to_british", "britishise_segments",
    # embed/base.py, and the store under index/lance.py
    "Embedder", "HashingEmbedder", "FastEmbedEmbedder", "model_fingerprint", "SearchIndex", "bm25",
    "build_indices", "build_scalar_indices", "ensure_vector_ids", "rebuild_vector_index", "replace_keys",
    "vector_schema", "sanitise_query", "sql_list", "sql_str", "date_lit",
    # the model client in rag/answer.py, the flow in api/app.py, the loader in config.py, the round robin
    "Answerer", "make_client", "cached_system", "usage_dict", "cache_key", "sse", "guarded", "item_exists", "take",
)


def test_no_copy_is_left_of_what_the_package_does_now():
    tracked = subprocess.run(["git", "ls-files", "src"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    for gone in REPLACED_MODULES:
        assert f"src/councils/{gone}" not in tracked, gone
    defined = subprocess.run(
        ["git", "grep", "-n", "-E", rf"^\s*(def|class) ({'|'.join(REPLACED_NAMES)})\b", "--", "src"],
        cwd=ROOT, capture_output=True, text=True, check=False).stdout
    assert defined == "", defined
    # and no stand-in kept so that an old import still works
    shims = subprocess.run(["git", "grep", "-n", "-i", "-E", r"backwards? compat|kept for (old|existing) imports|shim",
                            "--", "src"], cwd=ROOT, capture_output=True, text=True, check=False).stdout
    assert shims == "", shims
