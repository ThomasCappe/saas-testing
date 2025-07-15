# Outil simple pour charger des annonces immobilières depuis plusieurs flux RSS (sans scraping)
# Utilise Streamlit pour une interface visuelle

import feedparser
import streamlit as st
import pandas as pd

# Liste des flux RSS personnalisés de différents sites immobiliers (remplacer par des flux valides)
RSS_FEEDS = {
    "Leboncoin": "https://rss.app/feeds/i8XzbKPmhS4LsqVO.xml"
}

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

    for nom_site, url in RSS_FEEDS.items():
        flux = feedparser.parse(url)
        for entry in flux.entries[:nb_annonces]:
            if titre.lower() in entry.title.lower():
                toutes_annonces.append({
                    "Site": nom_site,
                    "Titre": entry.title,
                    "Prix": entry.get("price", "-"),  # si dispo
                    "Description": entry.summary,
                    "Lien": entry.link
                })

    if toutes_annonces:
        df = pd.DataFrame(toutes_annonces)
        st.success(f"{len(df)} annonces trouvées")
        st.dataframe(df)
        st.download_button("🔍 Télécharger CSV", df.to_csv(index=False), "annonces.csv")
    else:
        st.warning("Aucune annonce ne correspond au filtre actuel.")

else:
    st.write("Entrez un mot-clé et cliquez sur le bouton pour commencer.")
