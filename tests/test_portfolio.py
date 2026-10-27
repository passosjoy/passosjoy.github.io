import base64

import yaml

from portfolio import content as c
from portfolio.builder import build_site, fetch_data

CONFIG = yaml.safe_load(
    """
site: {title: T, description: D, url: "https://x.github.io", base_path: "", lang: pt-BR}
profile: {name: Joyce, role: DevOps, headline: H, about: "Sobre **mim**"}
github: {username: joy, exclude: [skipme]}
featured: [k8s-lab]
skills: [{group: Cloud, items: [OCI]}]
categories:
  Kubernetes: [kubernetes, k8s]
  Cloud: [oci, aws]
"""
)


def repo(name, **kw):
    base = {
        "name": name, "fork": False, "archived": False, "private": False, "topics": [],
        "description": None, "language": "Python", "default_branch": "main",
        "html_url": f"https://github.com/joy/{name}", "owner": {"login": "joy"},
        "pushed_at": "2026-01-02T00:00:00Z", "stargazers_count": 0,
    }
    base.update(kw)
    return base


class FakeClient:
    def __init__(self, repos, readmes):
        self._repos, self._readmes = repos, readmes

    def user(self, login):
        return {"login": login, "name": "Joyce", "avatar_url": "a.png"}

    def repos(self, login):
        return self._repos

    def readme(self, owner, name):
        text = self._readmes.get(name)
        return (text, "README.md") if text else (None, "")

    def languages(self, owner, name):
        return {"Python": 70, "HCL": 30}

    def contents(self, owner, name, path=""):
        return [{"name": "main.tf", "type": "file", "html_url": "u"}]


def test_fetch_filters_forks_excluded_and_self():
    client = FakeClient(
        [repo("k8s-lab"), repo("fork", fork=True), repo("skipme"), repo("joy.github.io"), repo("old", archived=True)],
        {"k8s-lab": "# Lab"},
    )
    data = fetch_data(client, CONFIG)
    assert [r["repo"]["name"] for r in data["repos"]] == ["k8s-lab"]


def test_relative_urls_rewritten():
    html = '<img src="docs/arch.png"><a href="guide.md#x">g</a><a href="https://a.b">e</a><a href="#top">t</a>'
    out = c.rewrite_relative_urls(html, "joy", "lab", "main")
    assert 'src="https://raw.githubusercontent.com/joy/lab/main/docs/arch.png"' in out
    assert 'href="https://github.com/joy/lab/blob/main/guide.md#x"' in out
    assert 'href="https://a.b"' in out and 'href="#top"' in out


def test_mermaid_and_summary():
    html, _ = c.render_markdown("```mermaid\nflowchart LR\n a-->b\n```\n")
    assert '<pre class="mermaid">flowchart LR\n a--&gt;b</pre>' in html
    assert c.extract_summary("# T\n\nEste laboratório provisiona um cluster Kubernetes local.") .startswith("Este laboratório")


def test_categories():
    assert c.detect_categories("Lab de Kubernetes na OCI", CONFIG["categories"]) == ["Kubernetes", "Cloud"]
    assert c.detect_categories("backstage", CONFIG["categories"]) == []


def test_build_site_generates_article_per_repo(tmp_path):
    client = FakeClient(
        [repo("k8s-lab", topics=["kubernetes"]), repo("empty-repo", pushed_at="2025-01-01T00:00:00Z")],
        {"k8s-lab": "# Kubernetes Lab\n\nProvisiona um cluster com kubectl e Helm para estudos.\n\n## Passo 1\n\n![d](img/d.png)\n"},
    )
    overrides = tmp_path / "content"
    overrides.mkdir()
    (overrides / "k8s-lab.md").write_text("---\nsummary: Resumo curado\n---\n## Problema\n\nX\n")
    out = tmp_path / "site"
    projects = build_site(fetch_data(client, CONFIG), CONFIG, out, overrides_dir=overrides)

    assert [p["slug"] for p in projects] == ["k8s-lab", "empty-repo"]
    article = (out / "projetos/k8s-lab/index.html").read_text()
    assert "Kubernetes Lab" in article and "Resumo curado" in article
    assert "Estudo de caso" in article and "raw.githubusercontent.com/joy/k8s-lab/main/img/d.png" in article
    assert "Documentação em construção" in (out / "projetos/empty-repo/index.html").read_text()
    index = (out / "index.html").read_text()
    assert "Sobre <strong>mim</strong>" in index and 'data-filter="Kubernetes"' in index
    assert (out / "sitemap.xml").exists() and (out / "feed.xml").exists() and (out / "static/css/style.css").exists()


def test_required_topic_and_empty_state(tmp_path):
    cfg = {**CONFIG, "github": {**CONFIG["github"], "required_topic": "portfolio"}}
    client = FakeClient([repo("tagged", topics=["portfolio"]), repo("untagged")], {})
    assert [r["repo"]["name"] for r in fetch_data(client, cfg)["repos"]] == ["tagged"]
    build_site({"user": {}, "repos": []}, cfg, tmp_path / "s", overrides_dir=tmp_path)
    assert "No resources found" in (tmp_path / "s/index.html").read_text()
