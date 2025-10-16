# app.py
# Interface utilisateur Streamlit pour l'agent d'analyse de contenu YouTube.

import streamlit as st
import pandas as pd
import os
import threading
import time
from youtube_agent import (
    run_full_analysis, 
    get_video_details, 
    get_cached_transcription,
    estimate_processing_time,
    format_time,
    get_average_processing_speed,
    TRANSCRIPTIONS_DIR
)
from pathlib import Path
from pytube import YouTube

st.set_page_config(page_title="Agent d'Analyse YouTube", layout="wide")

# Initialisation de l'état de la session
if 'video_df' not in st.session_state:
    st.session_state.video_df = None
if 'analysis_running' not in st.session_state:
    st.session_state.analysis_running = False
if 'stop_analysis' not in st.session_state:
    st.session_state.stop_analysis = False

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
        index=1,  # 'base' par défaut
        help="Les modèles plus grands sont plus précis mais beaucoup plus lents et gourmands en ressources. 'base' est un bon début."
    )

# --- Logique pour lister les vidéos ---
if list_videos_button and url_input:
    with st.spinner("Récupération des informations..."):
        videos_list = get_video_details(url_input)
        if videos_list:
            df = pd.DataFrame(videos_list)
            df.insert(0, "Sélectionner", True)
            st.session_state.video_df = df
        else:
            st.error("Impossible de récupérer les informations. Vérifiez l'URL.")
            st.session_state.video_df = None

# --- Fonction pour vérifier si une vidéo est en cache ---
def is_video_cached(url: str) -> bool:
    """Vérifie si une vidéo a déjà été transcrite"""
    return get_cached_transcription(url) is not None

# --- Affichage du sélecteur de vidéos et du panneau d'analyse ---
if st.session_state.video_df is not None:
    st.header("Vidéos à analyser")

    # Boutons pour sélectionner/désélectionner toutes les vidéos
    col_select_all, col_deselect_all = st.columns(2)
    
    select_all_clicked = False
    deselect_all_clicked = False
    
    with col_select_all:
        if st.button("✅ Tout sélectionner", key="select_all"):
            st.session_state.video_df["Sélectionner"] = True
            select_all_clicked = True
    
    with col_deselect_all:
        if st.button("❌ Tout désélectionner", key="deselect_all"):
            st.session_state.video_df["Sélectionner"] = False
            deselect_all_clicked = True

    # Ajouter une colonne indiquant si la vidéo est en cache
    df_display = st.session_state.video_df.copy()
    df_display["📁 Cached"] = df_display["url"].apply(
        lambda url: "✅ Disponible" if is_video_cached(url) else "⏳ À télécharger"
    )
    
    # Ajouter une colonne avec le temps estimé (sans appels YouTube pour éviter les timeouts)
    df_display["⏱️ Temps estimé"] = df_display.apply(
        lambda row: "✅ En cache" if "✅" in row["📁 Cached"] else "N/A",
        axis=1
    )
    
    # Trier pour que les vidéos en cache apparaissent en premier
    df_display = df_display.sort_values(
        "📁 Cached",
        key=lambda x: x.apply(lambda v: 0 if "✅" in str(v) else 1)
    ).reset_index(drop=True)

    edited_df = st.data_editor(
        df_display,
        column_config={
            "Sélectionner": st.column_config.CheckboxColumn(
                "Votre sélection",
                default=True,
            ),
            "title": st.column_config.TextColumn("Titre de la vidéo"),
            "duration": st.column_config.TextColumn("Durée"),
            "url": st.column_config.LinkColumn("URL", display_text="Lien"),
            "📁 Cached": st.column_config.TextColumn("État du cache"),
            "⏱️ Temps estimé": st.column_config.TextColumn("Temps estimé")
        },
        disabled=["title", "duration", "url", "📁 Cached", "⏱️ Temps estimé"],
        hide_index=True,
        height=400,
        key="video_selector"
    )

    selected_videos = edited_df[edited_df["Sélectionner"]]

    st.header("Lancer l'analyse locale")
    st.info(f"{len(selected_videos)} vidéo(s) sélectionnée(s) avec le modèle **{whisper_model}**.")
    
    # Afficher les estimations de temps (avec mise en cache)
    if len(selected_videos) > 0:
        avg_speed = get_average_processing_speed(whisper_model)
        
        # Calculer le temps estimé pour chaque vidéo
        estimated_times = []
        total_estimated_time = 0
        
        for idx, row in selected_videos.iterrows():
            url = row['url']
            title = row['title']
            # Vérifier d'abord si en cache
            if is_video_cached(url):
                estimated_time = 0
                estimated_times.append((title, 0))
            else:
                # Pour les vidéos non cachées, on utilise une estimation simple
                # On calcule le temps estimé quand on lance l'analyse
                estimated_times.append((title, None))
            
        if estimated_times:
            videos_to_process = sum(1 for _, t in estimated_times if t is None)
            if avg_speed and videos_to_process > 0:
                st.info(f"📊 **Vitesse moyenne** : {avg_speed:.2f}x (basée sur vidéos précédentes)")
            
            with st.expander(f"📋 Détails des {len(estimated_times)} vidéo(s) sélectionnée(s)"):
                for title, est_time in estimated_times:
                    if est_time == 0:
                        st.write(f"✅ {title[:60]} - En cache")
                    elif est_time is None:
                        st.write(f"⏳ {title[:60]} - À traiter")
                    else:
                        st.write(f"⏱️ {title[:60]} - {format_time(est_time)}")

    keywords_input = st.text_area(
        "Mots-clés à rechercher (séparés par des virgules)",
        placeholder="Ex: intelligence artificielle, éthique, philosophie"
    )

    # Créer deux colonnes pour les boutons
    col1, col2 = st.columns([4, 1])
    
    with col1:
        start_analysis = st.button("🚀 Lancer l'Analyse Locale", key="start_btn")
    
    with col2:
        stop_analysis = st.button("⏹️ Arrêter", key="stop_btn")
    
    if stop_analysis:
        st.session_state.stop_analysis = True

    if start_analysis:
        if selected_videos.empty:
            st.warning("Veuillez sélectionner au moins une vidéo à analyser.")
        elif not keywords_input:
            st.error("Veuillez renseigner les mots-clés.")
        else:
            video_urls_to_analyze = selected_videos['url'].tolist()
            keywords = [keyword.strip() for keyword in keywords_input.split(',')]

            st.session_state.analysis_running = True
            st.session_state.stop_analysis = False

            st.info(f"Lancement de l'analyse sur {len(video_urls_to_analyze)} vidéo(s)...")
            
            # Conteneurs pour les mises à jour en temps réel
            progress_container = st.container()
            status_container = st.container()
            time_container = st.container()
            results_container = st.container()

            progress_bar = progress_container.progress(0.0)
            status_text = status_container.empty()
            time_text = time_container.empty()
            current_progress = [0.0]  # Utiliser une liste pour modifier dans la closure
            analysis_start_time = [time.time()]  # Temps de démarrage
            videos_completed = [0]  # Nombre de vidéos complétées

            def update_progress(text):
                if st.session_state.stop_analysis:
                    return False  # Signaler l'arrêt
                status_text.markdown(f"**{text}**")
                # Incrémenter légèrement la progression à chaque appel
                current_progress[0] = min(current_progress[0] + 0.01, 0.99)
                progress_bar.progress(current_progress[0])
                
                # Déterminer si une vidéo a été complétée (texte contient "✅")
                if "✅" in text and "complétée" in text:
                    videos_completed[0] += 1
                
                # Calculer le temps écoulé et le temps restant estimé
                elapsed_time = time.time() - analysis_start_time[0]
                if videos_completed[0] > 0 and len(video_urls_to_analyze) > 0:
                    time_per_video = elapsed_time / videos_completed[0]
                    remaining_videos = len(video_urls_to_analyze) - videos_completed[0]
                    remaining_time = time_per_video * remaining_videos
                    time_text.info(f"⏱️ Temps écoulé : {format_time(elapsed_time)} | Temps restant estimé : {format_time(remaining_time)}")
                
                return True  # Continuer

            try:
                results = run_full_analysis(
                    video_urls_to_analyze, 
                    keywords, 
                    whisper_model, 
                    update_progress,
                    st.session_state.stop_analysis
                )

                if st.session_state.stop_analysis:
                    st.warning("⏹️ Analyse interrompue par l'utilisateur.")
                else:
                    progress_bar.progress(1.0)
                    status_text.success("✅ Analyse terminée !")
                    
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
            
            finally:
                st.session_state.analysis_running = False
                st.session_state.stop_analysis = False