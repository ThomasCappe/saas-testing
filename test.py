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
    print("=== Copie d'une archive Ansible depuis un remote vers un local ===\n")

    art_url = ask_input("URL Artifactory", "https://mon-artifactory.example.com/artifactory").rstrip("/")
    src_repo = ask_input("Repo source REMOTE")
    dst_repo = ask_input("Repo cible LOCAL")
    token = ask_input("Token", secret=True)
    raw = ask_input("Archive à copier (format namespace.collection:version)", "Community.general:1.0.0")

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
    code, body = api_post(search_url, token, body=aql.encode("utf-8"), content_type="text/plain")

    if code != 200:
        fail(f"échec recherche AQL\n{body}")

    data = json.loads(body)
    results = data.get("results", [])

    if not results:
        fail(
            f"archive introuvable dans {src_repo}: {archive_name}\n"
            f"Si le repo est remote, il faut peut-être d'abord résoudre/télécharger l'archive une fois pour la mettre en cache."
        )

    if len(results) > 1:
        print("\nPlusieurs résultats trouvés :", file=sys.stderr)
        for item in results:
            p = item["name"] if item["path"] == "." else f"{item['path']}/{item['name']}"
            print(f" - {item['repo']}/{p}", file=sys.stderr)
        fail("recherche ambiguë")

    item = results[0]
    path = item["path"]
    name = item["name"]

    relative_path = name if path == "." else f"{path}/{name}"

    encoded_src = urllib.parse.quote(relative_path, safe="/")
    encoded_to = urllib.parse.quote(f"/{dst_repo}/{relative_path}", safe="")

    copy_url = (
        f"{art_url}/api/copy/{src_repo}/{encoded_src}"
        f"?to={encoded_to}&suppressLayouts=1"
    )

    print(f"\nCopie de {src_repo}/{relative_path} vers {dst_repo}/{relative_path} ...")
    code, body = api_post(copy_url, token, body=b"")

    if code != 200:
        fail(f"échec copie\n{body}")

    print("\nCopie OK")
    print(f"Source      : {src_repo}/{relative_path}")
    print(f"Destination : {dst_repo}/{relative_path}")
    print(body)


if __name__ == "__main__":
    main()
