import streamlit as st
import pandas as pd
import os
import requests
from math import radians, cos, sin, sqrt, atan2
from datetime import datetime
import matplotlib.pyplot as plt
import re

st.set_page_config(menu_items=None, initial_sidebar_state="collapsed", page_title="Estimation Immo France", layout="wide")
st.title("\U0001F4CD Estimation gratuite de votre bien en France")
st.write("Obtenez une estimation gratuite en 1 minute, sans engagement.")

geo_cache = {}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def geocode_address(complete_address, user_lat=None, user_lon=None, max_distance_km=100):
    key = complete_address.strip().lower()
    if key in geo_cache:
        return geo_cache[key]
    try:
        url = f"https://api-adresse.data.gouv.fr/search/?q={complete_address}&limit=1"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        features = response.json().get("features", [])
        if not features:
            st.warning(f"Aucune coordonnée trouvée pour : {complete_address}")
            return None, None
        coords = features[0]["geometry"]["coordinates"]
        lat, lon = coords[1], coords[0]
        if user_lat is not None and user_lon is not None:
            dist = haversine(user_lat, user_lon, lat, lon)
            if dist > max_distance_km:
                st.warning(f"Adresse ignorée (trop loin) : {complete_address} → {round(dist)} km")
                return None, None
        geo_cache[key] = (lat, lon)
        return lat, lon
    except Exception as e:
        print(f"Erreur lors du géocodage de '{complete_address}' : {e}")
        return None, None

def get_postal_code_and_coords(addr):
    try:
        url = f"https://api-adresse.data.gouv.fr/search/?q={addr}&limit=1"
        response = requests.get(url)
        props = response.json()['features'][0]['properties']
        coords = response.json()['features'][0]['geometry']['coordinates']
        return props['postcode'], coords[1], coords[0]
    except:
        return None, None, None

def email_valide(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

def tel_valide(tel):
    tel_clean = tel.replace(" ", "").replace(".", "")
    return re.match(r"^0[1-9][0-9]{8}$", tel_clean)

addr_input = st.text_input("Adresse du bien")
suggestions = []
if addr_input:
    try:
        url = f"https://api-adresse.data.gouv.fr/search/?q={addr_input}&limit=5"
        response = requests.get(url)
        results = response.json()["features"]
        suggestions = [r["properties"]["label"] for r in results]
    except:
        suggestions = []

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
        action = st.selectbox("Projet", ["Vendre", "Estimer seulement"])
    condition = st.radio("État du bien", ["Neuf ou rénové", "À rénover"])
    years = st.multiselect("Années DVF", [2024, 2023, 2022, 2021], [2024, 2023])
    rayon = st.slider("Rayon autour (km)", 0.5, 5.0, 2.0, step=0.5)
    submit = st.form_submit_button("📨 Obtenir mon estimation")

leads_file = "leads.csv"

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
        for _, r in df.iterrows():
            try:
                val = float(r["Valeur fonciere"].replace(",", "."))
                surf = float(r["Surface reelle bati"].replace(",", "."))
                full_addr = f"{r.get('Voie', '')}, {r.get('Code postal', '')} {r.get('Commune', '')}"
                lat, lon = geocode_address(full_addr, user_lat, user_lon)
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
        series = pd.Series(prix_m2_list)
        series = series[(series >= series.quantile(0.1)) & (series <= series.quantile(0.9))]
        return series.mean(), len(series), pd.DataFrame(rows)
    return None, 0, pd.DataFrame()

if submit:
    progress = st.progress(0)
    with st.spinner("📊 Analyse en cours..."):
        progress.progress(10)

    if not email_valide(email):
        st.error("📧 Email invalide")
    elif not tel_valide(tel):
        st.error("📞 Numéro de téléphone invalide")
    elif not adresse:
        st.error("❗Veuillez sélectionner une adresse exacte")
    else:
        if not os.path.exists(leads_file):
            pd.DataFrame(columns=["Nom", "Email", "Téléphone", "Adresse", "Type", "Projet", "État", "Surface", "Estimation (€)", "Prix souhaité (€)", "Soumis le"]).to_csv(leads_file, index=False)
        progress.progress(20)
        cp_str, lat, lon = get_postal_code_and_coords(adresse)
        progress.progress(30)
        if cp_str and lat and lon:
            progress.progress(50)
            prix_m2, nb, df = get_local_dvf_estimation(cp_str, type_bien, years, lat, lon, rayon)
            progress.progress(70)
            if prix_m2 is not None:
                estim = surface * prix_m2
                progress.progress(90)

                # Enregistrement automatique du lead dans le fichier CSV
                lead_data = {
                    "Nom": nom,
                    "Email": email,
                    "Téléphone": tel,
                    "Adresse": adresse,
                    "Type": type_bien,
                    "Projet": action,
                    "État": condition,
                    "Surface": surface,
                    "Estimation (€)": round(estim),
                    "Prix souhaité (€)": prix_voulu,
                    "Soumis le": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Rappel demandé": "Non"
                }
                if os.path.exists(leads_file):
                    existing = pd.read_csv(leads_file)
                    lead_df = pd.DataFrame([lead_data])
                    for col in existing.columns:
                        if col not in lead_df.columns:
                            lead_df[col] = ""
                    lead_df = lead_df[existing.columns]
                    lead_df.to_csv(leads_file, mode='a', index=False, header=False)
                else:
                    pd.DataFrame([lead_data]).to_csv(leads_file, index=False)
                delta = round(((estim - prix_voulu) / prix_voulu) * 100) if prix_voulu else None
                if delta is not None:
                    if abs(delta) <= 5:
                        note = "Votre prix souhaité est cohérent avec l'estimation actuelle."
                    elif delta > 5:
                        note = f"L'estimation est environ {delta}% inférieure à votre prix souhaité. Pensez à ajuster pour optimiser la vente."
                    else:
                        note = f"L'estimation est environ {abs(delta)}% supérieure à votre prix souhaité. Cela pourrait indiquer une bonne opportunité."
                else:
                    note = ""
                st.info(f"🏡 D’après notre analyse du marché local, votre bien est estimé entre **{round(estim * 0.9)} €** et **{round(estim * 1.1)} €**. Cette fourchette reflète les tendances récentes observées dans votre zone géographique, en tenant compte du type de bien, de sa surface et de son état. Pour une estimation précise et adaptée à votre bien, n'hésitez pas à consulter un professionnel de l'immobilier qui pourra affiner cette analyse selon ses caractéristiques uniques.")
                if note:
                    st.markdown(f"💬 {note}")
                progress.progress(100)
                st.write(f"Basée sur {nb} ventes comparables")

                

                st.markdown("### 🧾 Coûts associés")
                st.markdown(f"• **Frais de notaire (ancien)** : {round(estim * 0.075)} € (environ 7.5%)")
                st.markdown(f"• **Frais de notaire (neuf)** : {round(estim * 0.03)} € (environ 3%)")
                st.markdown(f"• **Montant bas / haut estimé** : {round(estim * 0.9)} € - {round(estim * 1.1)} €")
                st.markdown(f"• **Taxe foncière (estimation)** : {round(estim * 0.012)} € (1.2% annuelle indicative)")
                if action == "Louer":
                    loyer_m2 = 12
                    loyer_mensuel = surface * loyer_m2
                    rendement = (loyer_mensuel * 12) / estim * 100
                    st.markdown(f"• **Loyer estimé** : {round(loyer_mensuel)} €/mois")
                    st.markdown(f"• **Rendement locatif brut estimé** : {round(rendement, 2)} %")
                df_temp = df.copy()
                df_temp["Année"] = pd.to_datetime(df_temp["Date mutation"], errors='coerce').dt.year
                moy = df_temp.groupby("Année")["Prix/m²"].mean()
                
                st.subheader("📊 Détails des ventes")
                st.dataframe(df)
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
                    "default": "Commerce"
                }
                st.subheader("🛍️ Commerces à proximité")
                data = get_nearby_pois(lat, lon)
                pois = []
                for el in data.get("elements", []):
                    t = el.get("tags", {})
                    cat = t.get("shop") or t.get("amenity", "default")
                    name = t.get("name") or TYPES_FR.get(cat, cat.title())
                    dist = round(haversine(lat, lon, el["lat"], el["lon"]), 2)
                    pois.append({"Nom": name, "Type": TYPES_FR.get(cat, cat.title()), "Distance (km)": dist})
                if pois:
                    df_pois = pd.DataFrame(pois).sort_values("Distance (km)")
                    st.dataframe(df_pois, use_container_width=True)
                    moyenne = sum(p["Distance (km)"] for p in pois) / len(pois)
                    st.markdown(f"**Score de proximité :** {round(moyenne, 2)} km")
                else:
                    st.info("Aucun commerce trouvé dans le rayon")

                # Analyse déplacée ici en bas
                st.subheader("📉 Analyse")
                st.line_chart(moy)

# Interface administrateur
if st.sidebar.checkbox("🔐 Mode Admin"):
    password = st.sidebar.text_input("Mot de passe", type="password")
    if password == "admin123":
        st.sidebar.success("Accès autorisé")
        st.header("📋 Liste des contacts clients")
        if os.path.exists(leads_file):
            df_leads = pd.read_csv(leads_file)
            filtre_date = st.date_input("Filtrer par date de soumission (optionnel)", value=None)
            if filtre_date:
                filtre_str = filtre_date.strftime("%Y-%m-%d")
                df_leads = df_leads[df_leads["Soumis le"].str.startswith(filtre_str)]
            if "Rappel demandé" in df_leads.columns:
                if st.checkbox("📞 Afficher uniquement les demandes de rappel"):
                    df_leads = df_leads[df_leads["Rappel demandé"] == "Oui"]
            def highlight_rappel(row):
                color = "background-color: #fff3cd" if row.get("Rappel demandé") == "Oui" else ""
                return [color] * len(row)

            st.dataframe(df_leads.style.apply(highlight_rappel, axis=1), use_container_width=True)
            st.download_button("⬇️ Télécharger les leads", df_leads.to_csv(index=False), file_name="leads.csv")
            if st.checkbox("🗑️ Supprimer un lead"):
                selected_index = st.number_input("Indice à supprimer (ligne)", min_value=0, max_value=len(df_leads)-1, step=1)
                if st.button("Supprimer"):
                    df_leads = df_leads.drop(index=selected_index).reset_index(drop=True)
                    df_leads.to_csv(leads_file, index=False)
                    st.success("Lead supprimé avec succès.")
            if st.button("🧹 Réinitialiser tous les leads"):
                os.remove(leads_file)
                st.success("Tous les leads ont été supprimés.")
        else:
            st.info("Aucun contact enregistré pour le moment.")
    else:
        if password:
            st.sidebar.error("Mot de passe incorrect")
