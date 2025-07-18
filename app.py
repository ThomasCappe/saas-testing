# Code complet de l'application avec synthèse du marché local, sans carte interactive

import streamlit as st
import pandas as pd
import os
import requests
from math import radians, cos, sin, sqrt, atan2
from time import sleep
import matplotlib.pyplot as plt

st.set_page_config(menu_items=None,
                 initial_sidebar_state="collapsed",page_title="Estimation Immo France", layout="wide")
st.title("📍 Estimation gratuite de votre bien en France")
st.write("Obtenez une estimation gratuite en 1 minute, sans engagement.")

# Utilitaires

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def autocomplete_address(query):
    try:
        url = f"https://api-adresse.data.gouv.fr/search/?q={query}&limit=5"
        response = requests.get(url)
        results = response.json()["features"]
        return [r["properties"]["label"] for r in results]
    except:
        return []

def get_postal_code_and_coords(addr):
    try:
        url = f"https://api-adresse.data.gouv.fr/search/?q={addr}&limit=1"
        response = requests.get(url)
        props = response.json()['features'][0]['properties']
        coords = response.json()['features'][0]['geometry']['coordinates']
        return props['postcode'], coords[1], coords[0]
    except:
        return None, None, None

def geocode_address(voie, commune):
    try:
        url = f"https://api-adresse.data.gouv.fr/search/?q={voie},{commune}&limit=1"
        response = requests.get(url)
        coords = response.json()['features'][0]['geometry']['coordinates']
        return coords[1], coords[0]
    except:
        return None, None

def get_local_dvf_estimation(cp, type_local, selected_years, user_lat, user_lon, rayon_km):
    prix_m2_list, rows = [], []
    for year in selected_years:
        fn = f"ValeursFoncieres-{year}.txt"
        if not os.path.exists(fn):
            continue
        cols_needed = ["Code postal", "Type local", "Nature mutation", "Surface reelle bati", "Valeur fonciere", "Voie", "Commune", "Date mutation"]
        df = pd.read_csv(fn, sep="|", usecols=lambda c: c in cols_needed, dtype=str)
        df = df[df["Code postal"] == cp]
        df = df[df["Type local"] == type_local]
        df = df[df["Nature mutation"] == "Vente"]
        df = df[df["Surface reelle bati"].notnull() & df["Valeur fonciere"].notnull()]
        for _, r in df.iterrows():
            try:
                val = float(r["Valeur fonciere"].replace(",", "."))
                surf = float(r["Surface reelle bati"].replace(",", "."))
                lat, lon = geocode_address(r.get("Voie", ""), r.get("Commune", ""))
                if not lat or not lon:
                    continue
                dist = haversine(user_lat, user_lon, lat, lon)
                if dist <= rayon_km:
                    prix_m2 = val / surf
                    prix_m2_list.append(prix_m2)
                    rows.append({
                        "Adresse": f"{r.get('Voie', '')}, {r.get('Commune', '')}",
                        "Prix/m²": round(prix_m2, 2),
                        "Surface (m²)": surf,
                        "Valeur foncière (€)": val,
                        "Distance (km)": round(dist, 2),
                        "Date mutation": r.get("Date mutation", "")
                    })
            except:
                continue
    if prix_m2_list:
        prix_m2_series = pd.Series(prix_m2_list)
        q1 = prix_m2_series.quantile(0.10)
        q9 = prix_m2_series.quantile(0.90)
        filtered = prix_m2_series[(prix_m2_series >= q1) & (prix_m2_series <= q9)]
        if not filtered.empty:
            prix_m2_list = filtered.tolist()
        return sum(prix_m2_list)/len(prix_m2_list), len(prix_m2_list), pd.DataFrame(rows)
    return None, 0, pd.DataFrame()

def get_nearby_pois(lat, lon, radius=2000):
    query = f"""
    [out:json];
    (
      node["shop"~"bakery|supermarket"](around:{radius},{lat},{lon});
      node["amenity"~"pharmacy|school|station"](around:{radius},{lat},{lon});
    );
    out;
    """
    url = "http://overpass-api.de/api/interpreter"
    resp = requests.get(url, params={"data": query})
    return resp.json()

TYPES_FR = {
    "bakery": "Boulangerie",
    "supermarket": "Supermarché",
    "pharmacy": "Pharmacie",
    "school": "École",
    "station": "Gare",
    "default": "Commerce",
    "Charging_Station": "Borne de recharge",
    "Driving_School": "Auto-Ecole",
    "Music_School": "Ecole de musique",
}

# Interface utilisateur — formulaire et estimation

addr_input = st.text_input("Adresse du bien")
suggestions = autocomplete_address(addr_input) if addr_input else []
adresse = st.selectbox("Adresse exacte", suggestions) if suggestions else ""

with st.form("form"):
    prix_voulu = st.number_input("Prix souhaité par le client (€)", min_value=0, step=1000)
    col1, col2 = st.columns(2)
    with col1:
        nom = st.text_input("Nom")
        email = st.text_input("Email")
        surface = st.number_input("Surface (m²)", 10, 1000)
    with col2:
        tel = st.text_input("Téléphone")
        type_bien = st.selectbox("Type", ["Appartement", "Maison"])
        action = st.selectbox("Projet", ["Vendre", "Louer", "Estimer seulement"])

    condition = st.radio("État du bien", ["Neuf ou rénové", "À rénover"])
    years = st.multiselect("Années DVF", [2024, 2023, 2022, 2021], [2024, 2023])
    rayon = st.slider("Rayon autour (km)", 0.5, 2.0, 1.0, step=0.1)
    submit = st.form_submit_button("📨 Obtenir mon estimation")

leads_file = "leads.csv"
if not os.path.exists(leads_file):
    pd.DataFrame(columns=["Nom", "Email", "Téléphone", "Adresse", "Type", "Projet", "État", "Surface", "Estimation (€)", "Prix souhaité (€)"]).to_csv(leads_file, index=False)

if submit and adresse:
    estim = None
    lead = pd.DataFrame([{
        "Nom": nom,
        "Email": email,
        "Téléphone": tel,
        "Adresse": adresse,
        "Type": type_bien,
        "Projet": action,
        "État": condition,
        "Surface": surface,
        "Estimation (€)": round(estim) if estim else None,
        "Prix souhaité (€)": prix_voulu
    }])
    lead.to_csv(leads_file, mode='a', header=False, index=False)
    progress = st.progress(0)
    with st.spinner("Chargement en cours..."):
        progress.progress(10)
        cp_str, lat, lon = get_postal_code_and_coords(adresse)
        progress.progress(30)
        cp = str(cp_str) if cp_str else None
        if cp and lat and lon:
            progress.progress(50)
            prix_m2, nb, df = get_local_dvf_estimation(cp, type_bien, years, lat, lon, rayon)
            progress.progress(70)
            if prix_m2:
                estim = surface * prix_m2
                bas, haut = (estim*0.9, estim) if condition == "À rénover" else (estim, estim*1.1)
                st.subheader(f"Estimation entre {round(bas)} € et {round(haut)} €")
                st.caption(f"Basé sur {nb} ventes similaires · Prix moyen : {round(prix_m2)} €/m²")
                st.info("Cette estimation est fournie à titre indicatif, basée uniquement sur les ventes passées.")
                st.warning("Pour une estimation fiable et personnalisée, une expertise par un professionnel de l'immobilier est recommandée.")

                frais_ancien = estim * 0.075
                frais_neuf = estim * 0.03
                st.markdown("**Frais de notaire estimés :**")
                st.markdown(f"• Ancien : **{round(frais_ancien)} €** (7.5%)")
                st.markdown(f"• Neuf : **{round(frais_neuf)} €** (3%)")

                if action == "Louer":
                    loyer_m2 = 12
                    loyer_mensuel = surface * loyer_m2
                    rendement = (loyer_mensuel * 12) / estim * 100
                    st.markdown(f"**Loyer estimé : {round(loyer_mensuel)} €/mois**")
                    st.markdown(f"**Rendement brut : {round(rendement, 2)} %**")

                with st.expander("Synthèse du marché local"):
                    if not df.empty:
                        min_m2 = df["Prix/m²"].min()
                        max_m2 = df["Prix/m²"].max()
                        ecart_type = df["Prix/m²"].std()
                        derniere = df["Date mutation"].dropna().max()
                        df['Année'] = pd.to_datetime(df['Date mutation'], errors='coerce').dt.year
                        yearly = df.groupby("Année")["Prix/m²"].mean().dropna()
                        tendance = ""
                        if len(yearly) >= 2:
                            delta = yearly.iloc[-1] - yearly.iloc[0]
                            if delta > 50:
                                tendance = "Hausse des prix"
                            elif delta < -50:
                                tendance = "Baisse des prix"
                            else:
                                tendance = "Prix stables"

                        st.markdown(f"**Date de la dernière vente :** {derniere}")
                        st.markdown(f"**Fourchette observée :** {round(min_m2)} €/m² à {round(max_m2)} €/m²")
                        st.markdown(f"**Écart-type :** {round(ecart_type)} €/m²")
                        st.markdown(f"**Tendance :** {tendance}")

                with st.expander("📊 Détails des ventes"):
                    st.dataframe(df, use_container_width=True)

                df_temp = df.copy()
                df_temp["Année"] = pd.to_datetime(df_temp["Date mutation"], errors='coerce').dt.year
                moy = df_temp.groupby("Année")["Prix/m²"].mean()

                st.subheader("📉 Analyse")
                st.subheader("📉 Évolution des prix et répartition des ventes")
                col1, col2 = st.columns(2)
                with col1:
                    fig1, ax1 = plt.subplots(figsize=(5, 3))
                    moy.plot(marker="o", ax=ax1)
                    ax1.set_ylabel("Prix moyen (€/m²)")
                    ax1.set_title("Prix moyen par an")
                    st.pyplot(fig1)

                with col2:
                    fig2, ax2 = plt.subplots(figsize=(5, 3))
                    df["Prix/m²"].hist(bins=20, ax=ax2, color="#69b3a2")
                    ax2.set_xlabel("€/m²")
                    ax2.set_ylabel("Nombre de ventes")
                    ax2.set_title("Distribution des ventes")
                    st.pyplot(fig2)

                st.subheader("🛍️ Commerces à proximité")
                progress.progress(90)
                data = get_nearby_pois(lat, lon)
                pois = []
                for el in data["elements"]:
                    t = el.get("tags", {})
                    cat = t.get("shop") or t.get("amenity", "default")
                    name = t.get("name") or TYPES_FR.get(cat, cat.title())
                    dist = round(haversine(lat, lon, el["lat"], el["lon"]), 2)
                    pois.append({"Nom": name, "Type": TYPES_FR.get(cat, cat.title()), "Distance (km)": dist})

                progress.progress(100)
                if pois:
                    df_pois = pd.DataFrame(pois).sort_values("Distance (km)")
                    st.dataframe(df_pois, use_container_width=True)
                    moyenne = sum(p["Distance (km)"] for p in pois) / len(pois)
                    st.markdown(f"**Score de proximité :** {round(moyenne,2)} km")
                else:
                    st.info("Aucun commerce trouvé dans le rayon")
        else:
            st.error("Adresse non trouvée")

# Interface admin pour visualiser les leads
if st.sidebar.checkbox("🛠️ Mode Admin"):
    password = st.sidebar.text_input("Mot de passe", type="password")
    if password == "admin123":
        st.header("📋 Liste des contacts clients")
        if os.path.exists(leads_file):
            df_leads = pd.read_csv(leads_file)
            st.dataframe(df_leads, use_container_width=True)
            st.download_button("⬇️ Télécharger les leads", df_leads.to_csv(index=False), file_name="leads.csv")
        else:
            st.info("Aucun contact enregistré pour le moment.")
    else:
        st.sidebar.warning("Mot de passe incorrect.")
