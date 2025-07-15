# Outil simple pour charger des annonces immobilières depuis plusieurs sources
# Utilise Streamlit pour une interface visuelle + Playwright pour Leboncoin

import feedparser
import streamlit as st
import pandas as pd
import asyncio
from playwright.sync_api import sync_playwright

# Liste des flux RSS personnalisés de différents sites immobiliers (RSS uniquement)
RSS_FEEDS = {
    "PAP": "https://www.pap.fr/rss/annonces",
    "ParuVendu": "https://www.paruvendu.fr/immobilier/rss/?k=appartement+marseille"
}

# Fonction pour extraire les annonces Leboncoin avec Playwright
def get_leboncoin_results(query, max_results=10):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        url = f"https://www.leboncoin.fr/recherche?text={query.replace(' ', '%20')}"
        page.goto(url)
        page.wait_for_timeout(3000)
        listings = page.locator(".styles_adCard__2YFTi").all()[:max_results]

        for listing in listings:
            try:
                title = listing.locator(".styles_adTitle__1yVoT").inner_text()
                link = listing.locator("a").get_attribute("href")
                price = listing.locator(".styles_price__2x2UJ").inner_text()
                results.append({
                    "Site": "Leboncoin",
                    "Titre": title,
                    "Prix": price,
                    "Description": "",
                    "Lien": f"https://www.leboncoin.fr{link}" if link.startswith("/") else link
                })
            except:
                continue

        browser.close()
    return results

# Interface utilisateur
st.set_page_config(page_title="Générateur d'annonces Immo", layout="centered")
st.title("🏠 Annonces Immo Automatisées")

# Entrées utilisateur
titre = st.text_input("Titre de recherche (ville, type, etc.)", value="appartement marseille")
nb_annonces = st.slider("Nombre d'annonces à charger par site", min_value=5, max_value=50, value=10)

# Bouton principal
if st.button("➕ Charger les annonces"):
    st.info("Chargement en cours...")
    toutes_annonces = []

    # Flux RSS
    for nom_site, url in RSS_FEEDS.items():
        flux = feedparser.parse(url)
        for entry in flux.entries[:nb_annonces]:
            if titre.lower() in entry.title.lower():
                toutes_annonces.append({
                    "Site": nom_site,
                    "Titre": entry.title,
                    "Prix": entry.get("price", "-"),
                    "Description": entry.summary,
                    "Lien": entry.link
                })

    # Ajout Leboncoin via Playwright
    st.info("Chargement des annonces Leboncoin...")
    try:
        lbc_annonces = get_leboncoin_results(titre, nb_annonces)
        toutes_annonces.extend(lbc_annonces)
    except Exception as e:
        st.error(f"Erreur lors du chargement Leboncoin: {e}")

    # Affichage
    if toutes_annonces:
        df = pd.DataFrame(toutes_annonces)
        st.success(f"{len(df)} annonces trouvées")
        st.dataframe(df)
        st.download_button("🔍 Télécharger CSV", df.to_csv(index=False), "annonces.csv")
    else:
        st.warning("Aucune annonce ne correspond au filtre actuel.")

else:
    st.write("Entrez un mot-clé et cliquez sur le bouton pour commencer.")
