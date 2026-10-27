#!/usr/bin/env python3
"""Gera o portfólio estático a partir dos repositórios públicos do GitHub."""
import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from portfolio.builder import build_site, fetch_data
from portfolio.github import GitHubClient


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="_site")
    parser.add_argument("--from-json", help="usa dados salvos em vez de chamar a API do GitHub")
    parser.add_argument("--dump-json", help="salva os dados obtidos da API neste arquivo")
    args = parser.parse_args(argv)

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    else:
        client = GitHubClient(token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
        data = fetch_data(client, config)
    if args.dump_json:
        Path(args.dump_json).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    projects = build_site(data, config, args.out)
    print(f"Site gerado em {args.out}/ com {len(projects)} projetos:")
    for p in projects:
        print(f"  - {p['title']} ({', '.join(p['categories']) or 'sem categoria'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
