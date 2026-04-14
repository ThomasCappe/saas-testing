#!/usr/bin/env python3
import json
import sys
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from getpass import getpass


def fail(msg, code=1):
    print(f"\nERREUR: {msg}", file=sys.stderr)
    sys.exit(code)


def ask_input(label, default=None, secret=False):
    prompt = f"{label}"
    if default is not None:
        prompt += f" [{default}]"
    prompt += " : "

    value = getpass(prompt) if secret else input(prompt)
    value = value.strip()

    if not value and default is not None:
        return default
    return value


def api_post(url, token, body=b"", content_type=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main():
    print("=== Déplacement d'une archive Ansible Artifactory ===\n")

    art_url = ask_input("URL Artifactory", "https://mon-artifactory.example.com/artifactory").rstrip("/")
    src_repo = ask_input("Repo source (laisser vide pour recherche automatique)")
    dst_repo = ask_input("Repo cible", "internal-ansible-prod")
    token = ask_input("Token", secret=True)
    raw = ask_input("Archive à déplacer (format namespace.collection:version)", "Community.general:1.0.0")

    if not token:
        fail("token vide")

    if ":" not in raw:
        fail("format attendu: namespace.collection:version")

    collection, version = raw.split(":", 1)
    collection = collection.strip().lower()
    version = version.strip()

    if "." not in collection:
        fail("le nom doit être de la forme namespace.collection")

    archive_name = f"{collection.replace('.', '-')}-{version}.tar.gz"

    if src_repo:
        aql = f'''items.find({{
  "repo": "{src_repo}",
  "name": "{archive_name}"
}}).include("repo","path","name")'''
    else:
        aql = f'''items.find({{
  "name": "{archive_name}"
}}).include("repo","path","name")'''

    search_url = f"{art_url}/api/search/aql"
    code, body = api_post(search_url, token, body=aql.encode("utf-8"), content_type="text/plain")

    if code != 200:
        fail(f"échec recherche AQL\n{body}")

    data = json.loads(body)
    results = data.get("results", [])

    if not results:
        fail(f"archive introuvable: {archive_name}")

    # On évite de tester le repo cible comme source
    candidates = [r for r in results if r["repo"] != dst_repo]

    if not candidates:
        fail("aucune source exploitable trouvée")

    print("\nCandidats trouvés :")
    for item in candidates:
        p = item["name"] if item["path"] == "." else f"{item['path']}/{item['name']}"
        print(f" - {item['repo']}/{p}")

    errors = []

    for item in candidates:
        repo = item["repo"]
        path = item["path"]
        name = item["name"]

        relative_path = name if path == "." else f"{path}/{name}"

        encoded_src = urllib.parse.quote(relative_path, safe="/")
        encoded_to = urllib.parse.quote(f"/{dst_repo}/{relative_path}", safe="")

        move_url = (
            f"{art_url}/api/move/{repo}/{encoded_src}"
            f"?to={encoded_to}&suppressLayouts=1"
        )

        print(f"\nTest move depuis {repo} ...")
        code, body = api_post(move_url, token, body=b"")

        if code == 200:
            print("\nDéplacement OK")
            print(f"Source      : {repo}/{relative_path}")
            print(f"Destination : {dst_repo}/{relative_path}")
            print(body)
            return

        lowered = body.lower()
        if "not a local repository" in lowered or "repository is not a local repository" in lowered:
            print(f" -> {repo} ignoré : pas un repo local")
            continue

        errors.append(f"{repo}: HTTP {code} - {body}")

    fail(
        "aucun repo local valide trouvé pour faire le move.\n\n"
        "Soit ton archive n'est présente que dans un virtual/remote,\n"
        "soit il faut donner directement le vrai repo local source.\n\n"
        + ("\n\nDétails:\n- " + "\n- ".join(errors) if errors else "")
    )


if __name__ == "__main__":
    main()
