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
            return resp.read().decode("utf-8")
    except HTTPError as e:
        details = e.read().decode("utf-8", errors="replace")
        fail(f"HTTP {e.code} sur {url}\n{details}")


def ask_input(label, default=None, secret=False):
    if default:
        prompt = f"{label} [{default}] : "
    else:
        prompt = f"{label} : "

    value = getpass(prompt) if secret else input(prompt)
    value = value.strip()

    if not value and default is not None:
        return default
    return value


def main():
    print("=== Déplacement d'une archive Ansible Artifactory ===\n")

    art_url = ask_input("URL Artifactory", "https://mon-artifactory.example.com/artifactory").rstrip("/")
    src_repo = ask_input("Repo source", "internal-ansible-dev")
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

    aql = f'''items.find({{
  "repo": "{src_repo}",
  "name": "{archive_name}"
}}).include("repo","path","name")'''

    search_url = f"{art_url}/api/search/aql"
    search_resp = api_post(search_url, token, body=aql.encode("utf-8"), content_type="text/plain")
    search_data = json.loads(search_resp)
    results = search_data.get("results", [])

    if not results:
        fail(f"archive introuvable dans {src_repo}: {archive_name}")

    if len(results) > 1:
        print(f"\nPlusieurs résultats trouvés pour {archive_name} dans {src_repo} :", file=sys.stderr)
        for item in results:
            print(f" - {item['repo']}/{item['path']}/{item['name']}", file=sys.stderr)
        fail("recherche ambiguë")

    item = results[0]
    src_path = item["path"]
    src_name = item["name"]

    if src_path == ".":
        relative_path = src_name
    else:
        relative_path = f"{src_path}/{src_name}"

    encoded_src = urllib.parse.quote(relative_path, safe="/")
    encoded_to = urllib.parse.quote(f"/{dst_repo}/{relative_path}", safe="")

    move_url = (
        f"{art_url}/api/move/{src_repo}/{encoded_src}"
        f"?to={encoded_to}&suppressLayouts=1"
    )

    move_resp = api_post(move_url, token, body=b"")

    print("\nDéplacement OK")
    print(f"Source      : {src_repo}/{relative_path}")
    print(f"Destination : {dst_repo}/{relative_path}")
    print(move_resp)


if __name__ == "__main__":
    main()
