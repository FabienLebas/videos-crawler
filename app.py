# app.py
# Interface utilisateur Streamlit pour l'agent d'analyse de contenu YouTube.

import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from youtube_agent import run_full_analysis, get_video_details

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

st.set_page_config(page_title="Agent d'Analyse YouTube", layout="wide")

# Initialisation de l'état de la session
if 'video_df' not in st.session_state:
    st.session_state.video_df = None

st.title("🤖 Agent d'Analyse de Contenu YouTube")
st.markdown("""
Cette application analyse les vidéos sélectionnées d'une chaîne YouTube pour y trouver des mots-clés.
**Étape 1 :** Listez les vidéos d'une chaîne. **Étape 2 :** Sélectionnez les vidéos à analyser et lancez l'analyse.
""")

# --- ONGLETS PRINCIPAUX ---
tab1, tab2 = st.tabs(["📊 Analyse complète", "🧪 Test vidéo unique"])

# === TAB 1: ANALYSE COMPLÈTE ===
with tab1:
    # --- Panneau de configuration dans la barre latérale ---
    with st.sidebar:
        st.header("Étape 1 : Lister les vidéos")
        channel_url = st.text_input(
            "URL de la chaîne YouTube",
            placeholder="Ex: https://www.youtube.com/@monsieurphi"
        )
        list_videos_button = st.button("Lister les vidéos de la chaîne")

    # --- Logique pour lister les vidéos ---
    if list_videos_button and channel_url:
        with st.spinner("Récupération des informations des vidéos... Cela peut prendre un moment."):
            videos_list = get_video_details(channel_url)
            if videos_list:
                df = pd.DataFrame(videos_list)
                df.insert(0, "Sélectionner", False)
                st.session_state.video_df = df
            else:
                st.error("Impossible de récupérer les vidéos. Vérifiez l'URL de la chaîne.")
                st.session_state.video_df = None

    # --- Affichage du sélecteur de vidéos et du panneau d'analyse ---
    if st.session_state.video_df is not None:
        st.header("Sélectionnez les vidéos à analyser")

        edited_df = st.data_editor(
            st.session_state.video_df,
            column_config={
                "Sélectionner": st.column_config.CheckboxColumn(
                    "Votre sélection",
                    default=False,
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

        st.header("Étape 2 : Lancer l'analyse")
        st.info(f"{len(selected_videos)} vidéo(s) sélectionnée(s).")

        keywords_input = st.text_area(
            "Mots-clés à rechercher (séparés par des virgules)",
            placeholder="Ex: intelligence artificielle, éthique, philosophie"
        )

        start_analysis = st.button("Lancer l'Analyse sur la sélection")

        if start_analysis:
            openai_api_key = os.getenv("OPENAI")

            if selected_videos.empty:
                st.warning("Veuillez sélectionner au moins une vidéo à analyser.")
            elif not keywords_input or not openai_api_key:
                st.error("Veuillez renseigner les mots-clés. Assurez-vous également que votre variable d'environnement OPENAI est bien configurée dans un fichier .env.")
            else:
                video_urls_to_analyze = selected_videos['url'].tolist()
                keywords = [keyword.strip() for keyword in keywords_input.split(',')]

                st.info(f"Lancement de l'analyse sur {len(video_urls_to_analyze)} vidéo(s)...")
                progress_bar = st.progress(0.0)
                status_text = st.empty()

                def update_progress(progress, text):
                    progress_bar.progress(progress)
                    status_text.text(text)

                try:
                    results = run_full_analysis(video_urls_to_analyze, keywords, openai_api_key, update_progress)

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

# === TAB 2: TEST VIDÉO UNIQUE ===
with tab2:
    st.header("🧪 Testez avec une vidéo unique")
    st.markdown("Testez rapidement si l'analyse fonctionne avec une vidéo en particulier.")

    test_video_url = st.text_input(
        "URL de la vidéo YouTube",
        placeholder="Ex: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )

    test_keywords_input = st.text_area(
        "Mots-clés à chercher (séparés par des virgules)",
        placeholder="Ex: test, exemple, mot",
        key="test_keywords"
    )

    if st.button("Lancer le test"):
        openai_api_key = os.getenv("OPENAI")

        if not test_video_url:
            st.warning("Veuillez entrer une URL de vidéo.")
        elif not test_keywords_input or not openai_api_key:
            st.error("Veuillez renseigner les mots-clés. Assurez-vous également que votre clé API OPENAI est configurée.")
        else:
            keywords = [keyword.strip() for keyword in test_keywords_input.split(',')]

            st.info(f"Test en cours sur 1 vidéo avec {len(keywords)} mot(s)-clé(s)...")
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            def update_test_progress(progress, text):
                progress_bar.progress(progress)
                status_text.text(text)

            try:
                results = run_full_analysis([test_video_url], keywords, openai_api_key, update_test_progress)

                st.success("✅ Test terminé !")
                st.header("📋 Résultats du test")

                if results and results['total_occurrences'] > 0:
                    st.metric("Occurrences totales trouvées", results['total_occurrences'])

                    for keyword in keywords:
                        hits = results['details'].get(keyword, [])
                        if hits:
                            title, url, count = hits[0]
                            st.success(f"**'{keyword}'** trouvé **{count}** fois")
                            st.markdown(f"Titre : {title}")
                        else:
                            st.warning(f"**'{keyword}'** : 0 occurrence")
                else:
                    st.info("Aucune occurrence des mots-clés n'a été trouvée dans cette vidéo.")

            except Exception as e:
                st.error(f"Erreur lors du test : {e}")