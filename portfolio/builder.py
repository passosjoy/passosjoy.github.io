import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from . import content as c

ROOT = Path(__file__).resolve().parent.parent


def is_included(repo, config):
    gh_cfg = config["github"]
    login = gh_cfg["username"].lower()
    exclude = {name.lower() for name in gh_cfg.get("exclude", [])} | {login, f"{login}.github.io"}
    if repo["name"].lower() in exclude or repo.get("private"):
        return False
    if repo.get("fork") and not gh_cfg.get("include_forks", False):
        return False
    if repo.get("archived") and not gh_cfg.get("include_archived", False):
        return False
    required = gh_cfg.get("required_topic")
    return not required or required in (repo.get("topics") or [])


def fetch_data(client, config):
    login = config["github"]["username"]
    user = client.user(login) or {"login": login}
    repos = []
    for repo in client.repos(login):
        if not is_included(repo, config):
            continue
        readme, readme_path = client.readme(login, repo["name"])
        repos.append(
            {
                "repo": repo,
                "readme": readme or "",
                "readme_path": readme_path,
                "languages": client.languages(login, repo["name"]),
                "tree": [
                    {"name": i["name"], "type": i["type"], "url": i.get("html_url")}
                    for i in client.contents(login, repo["name"])
                ],
            }
        )
    return {"user": user, "repos": repos, "fetched_at": datetime.now(timezone.utc).isoformat()}


def load_overrides(directory):
    overrides = {}
    for path in sorted(Path(directory).glob("*.md")):
        if path.name.startswith("_"):
            continue
        meta, body = c.parse_frontmatter(path.read_text(encoding="utf-8"))
        overrides[(meta.get("repo") or path.stem).lower()] = {"meta": meta, "body": body}
    return overrides


def build_project(entry, config, override=None):
    repo = entry["repo"]
    owner = repo["owner"]["login"] if "owner" in repo else config["github"]["username"]
    branch = repo.get("default_branch", "main")
    readme = entry.get("readme", "")
    meta = (override or {}).get("meta", {})
    case_study_md = (override or {}).get("body", "").strip()

    readme_dir = c.posixpath.dirname(entry.get("readme_path") or "")
    lab_html, lab_toc = ("", [])
    if readme.strip():
        lab_html, lab_toc = c.render_markdown(c.remove_first_h1(readme))
        lab_html = c.rewrite_relative_urls(lab_html, owner, repo["name"], branch, readme_dir)

    case_html, case_toc = ("", [])
    if case_study_md:
        case_html, case_toc = c.render_markdown(case_study_md)
        case_html = c.rewrite_relative_urls(case_html, owner, repo["name"], branch)

    languages = entry.get("languages") or {}
    total = sum(languages.values()) or 1
    lang_list = [
        {"name": k, "pct": round(v * 100 / total, 1)}
        for k, v in sorted(languages.items(), key=lambda kv: -kv[1])
    ]

    topics = repo.get("topics") or []
    title = meta.get("title") or c.extract_title(readme) or c.prettify_name(repo["name"])
    summary = (
        meta.get("summary")
        or repo.get("description")
        or c.extract_summary(readme)
        or "Laboratório prático — documentação em evolução."
    )
    haystack = " ".join(
        [repo["name"], repo.get("description") or "", " ".join(topics), " ".join(languages), readme[:4000], case_study_md]
    )
    categories = meta.get("categories") or c.detect_categories(haystack, config.get("categories", {}))
    featured_cfg = {n.lower() for n in config.get("featured", [])}
    pushed = repo.get("pushed_at") or repo.get("updated_at") or repo.get("created_at")

    return {
        "name": repo["name"],
        "slug": c.slugify(repo["name"]),
        "title": title,
        "summary": summary,
        "url": repo.get("html_url") or f"https://github.com/{owner}/{repo['name']}",
        "homepage": repo.get("homepage") or meta.get("demo"),
        "topics": topics,
        "categories": categories,
        "languages": lang_list,
        "language": repo.get("language"),
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "created_at": repo.get("created_at"),
        "pushed_at": pushed,
        "pushed_label": _date_label(pushed),
        "featured": bool(meta.get("featured")) or repo["name"].lower() in featured_cfg,
        "order": meta.get("order", 1000),
        "stack": meta.get("stack", []),
        "case_study_html": case_html,
        "lab_html": lab_html,
        "toc": case_toc + lab_toc,
        "has_mermaid": 'class="mermaid"' in case_html + lab_html,
        "reading_time": c.reading_time(case_study_md + "\n" + readme),
        "tree": entry.get("tree", []),
        "branch": branch,
    }


def _date_label(iso):
    if not iso:
        return ""
    months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f"{months[dt.month - 1]} {dt.year}"


def build_site(data, config, out_dir, overrides_dir=None, templates_dir=None, static_dir=None):
    out = Path(out_dir)
    overrides = load_overrides(overrides_dir or ROOT / "content" / "projects")
    projects = [
        build_project(e, config, overrides.get(e["repo"]["name"].lower()))
        for e in data["repos"]
        if is_included(e["repo"], config)
    ]
    projects.sort(key=lambda p: p["pushed_at"] or "", reverse=True)
    featured = sorted([p for p in projects if p["featured"]], key=lambda p: (p["order"], p["name"].lower()))
    categories = sorted({cat for p in projects for cat in p["categories"]})

    site = dict(config["site"])
    site["base_path"] = site.get("base_path", "").rstrip("/")
    site["url"] = site.get("url", "").rstrip("/")
    user = data.get("user", {})
    profile = dict(config.get("profile", {}))
    profile.setdefault("name", user.get("name") or user.get("login"))
    profile.setdefault("avatar", user.get("avatar_url"))
    profile.setdefault("github", f"https://github.com/{config['github']['username']}")

    env = Environment(
        loader=FileSystemLoader(str(templates_dir or ROOT / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["markdown"] = lambda text: Markup(c.render_markdown(text or "")[0])
    now = datetime.now(timezone.utc)
    ctx = {
        "site": site,
        "profile": profile,
        "config": config,
        "projects": projects,
        "featured": featured,
        "categories": categories,
        "generated_at": now,
        "stats": {
            "projects": len(projects),
            "languages": len({l["name"] for p in projects for l in p["languages"]}),
            "categories": len(categories),
        },
    }

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(static_dir or ROOT / "static", out / "static")

    def write(rel, template, **extra):
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(**ctx, **extra), encoding="utf-8")

    write("index.html", "index.html", page="home")
    write("projetos/index.html", "projects.html", page="projects")
    for project in projects:
        write(f"projetos/{project['slug']}/index.html", "project.html", page="project", project=project)
    write("404.html", "404.html", page="404")
    write("sitemap.xml", "sitemap.xml")
    write("feed.xml", "feed.xml")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site['url']}/sitemap.xml\n")
    (out / ".nojekyll").write_text("")
    (out / "projects.json").write_text(
        json.dumps(
            [{k: p[k] for k in ("name", "slug", "title", "summary", "url", "categories", "topics", "pushed_at")} for p in projects],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return projects
