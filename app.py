# app.py
# Interface utilisateur Streamlit pour l'agent d'analyse de contenu YouTube.

import streamlit as st
import pandas as pd
import os
# La bibliothèque dotenv n'est plus nécessaire si on n'utilise plus de clés API
# from dotenv import load_dotenv
from youtube_agent import run_full_analysis, get_video_details

# # Charger les variables d'environnement (plus nécessaire)
# load_dotenv()

st.set_page_config(page_title="Agent d'Analyse YouTube", layout="wide")

# Initialisation de l'état de la session
if 'video_df' not in st.session_state:
    st.session_state.video_df = None

st.title("🤖 Agent d'Analyse de Contenu YouTube (Version Locale)")
st.markdown("""
Cette application utilise le modèle **Whisper auto-hébergé** pour analyser les vidéos d'une chaîne YouTube.
**Étape 1 :** Listez les vidéos. **Étape 2 :** Sélectionnez les vidéos et le modèle, puis lancez l'analyse.
""")

# --- Panneau de configuration dans la barre latérale ---
with st.sidebar:
    st.header("Configuration de l'Analyse")
    
    st.subheader("Étape 1 : Lister les vidéos")
    url_input = st.text_input(
        "URL de la chaîne ou d'une vidéo",
        placeholder="Collez une URL ici..."
    )
    list_videos_button = st.button("Lister la/les vidéo(s)")

    st.subheader("Étape 2 : Choisir le modèle")
    whisper_model = st.selectbox(
        "Taille du modèle Whisper",
        ("tiny", "base", "small", "medium", "large-v2"),
        index=1, # 'base' par défaut
        help="Les modèles plus grands sont plus précis mais beaucoup plus lents et gourmands en ressources. 'base' est un bon début."
    )

# --- Logique pour lister les vidéos ---
if list_videos_button and url_input:
    with st.spinner("Récupération des informations..."):
        videos_list = get_video_details(url_input)
        if videos_list:
            df = pd.DataFrame(videos_list)
            df.insert(0, "Sélectionner", True) # Tout sélectionner par défaut
            st.session_state.video_df = df
        else:
            st.error("Impossible de récupérer les informations. Vérifiez l'URL.")
            st.session_state.video_df = None

# --- Affichage du sélecteur de vidéos et du panneau d'analyse ---
if st.session_state.video_df is not None:
    st.header("Vidéos à analyser")

    edited_df = st.data_editor(
        st.session_state.video_df,
        column_config={
            "Sélectionner": st.column_config.CheckboxColumn(
                "Votre sélection",
                default=True,
            ),
            "title": st.column_config.TextColumn("Titre de la vidéo"),
            "duration": st.column_config.TextColumn("Durée"),
            "url": st.column_config.LinkColumn("URL", display_text="Lien")
        },
        disabled=["title", "duration", "url"],
        hide_index=True,
        height=400
    )

    selected_videos = edited_df[edited_df.Sélectionner]

    st.header("Lancer l'analyse locale")
    st.info(f"{len(selected_videos)} vidéo(s) sélectionnée(s) avec le modèle **{whisper_model}**.")

    keywords_input = st.text_area(
        "Mots-clés à rechercher (séparés par des virgules)",
        placeholder="Ex: intelligence artificielle, éthique, philosophie"
    )

    start_analysis = st.button("Lancer l'Analyse Locale")

    if start_analysis:
        if selected_videos.empty:
            st.warning("Veuillez sélectionner au moins une vidéo à analyser.")
        elif not keywords_input:
            st.error("Veuillez renseigner les mots-clés.")
        else:
            video_urls_to_analyze = selected_videos['url'].tolist()
            keywords = [keyword.strip() for keyword in keywords_input.split(',')]

            st.info(f"Lancement de l'analyse sur {len(video_urls_to_analyze)} vidéo(s)...")
            st.warning("Le premier chargement du modèle peut être long (plusieurs minutes) car il est téléchargé.")
            
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            def update_progress(progress, text):
                progress_bar.progress(progress)
                status_text.text(text)

            try:
                # On passe maintenant le nom du modèle au lieu de la clé API
                results = run_full_analysis(video_urls_to_analyze, keywords, whisper_model, update_progress)

                st.success("✅ Analyse terminée !")
                st.header("📊 Rapport d'Analyse")

                if results:
                    col1, col2 = st.columns(2)
                    col1.metric("Nombre de vidéos analysées", results['total_videos'])
                    col2.metric("Total des occurrences trouvées", results['total_occurrences'])

                    st.subheader("Détails par mot-clé")

                    if results['total_occurrences'] == 0:
                        st.info("Aucune occurrence des mots-clés spécifiés n'a été trouvée.")
                    else:
                        for keyword in keywords:
                            hits = results['details'].get(keyword, [])
                            with st.expander(f"'{keyword}' - {len(hits)} vidéo(s) correspondante(s)"):
                                if hits:
                                    for title, url, count in hits:
                                        st.markdown(f"**{title}**")
                                        st.markdown(f" - **Occurrences :** {count}")
                                        st.markdown(f" - **URL :** [{url}]({url})")
                                else:
                                    st.write("Aucune occurrence trouvée pour ce mot-clé.")
                else:
                    st.error("L'analyse n'a retourné aucun résultat.")

            except Exception as e:
                st.error(f"Une erreur critique est survenue durant l'analyse : {e}")

