import streamlit as st
import os
import time
import pandas as pd

from services.auth.login_wall import render_login_wall
from services.state.session_defaults import initial_session_defaults
from services.config.workout_config import EXERCISE_OPTIONS
from services.ui.style_loader import load_css, inject_local_font, inject_webrtc_styles
from services.persistence.exercise_repository import init_db
from services.persistence.exercise_repository import get_users_exercises


# =========================
# LAZY IMPORT HELPERS
# =========================

def get_webrtc():
    from streamlit_webrtc import webrtc_streamer, WebRtcMode
    return webrtc_streamer, WebRtcMode


def get_video_processor():
    from services.vision.exercise_video_processor import VideoProcessorClass
    return VideoProcessorClass


def get_groq():
    from groq import Groq
    return Groq


def get_coach():
    from services.coaching.llm import LLMCoach
    from services.coaching.tts import TextToSpeech
    from services.coaching.voice_pipeline import VoicePipeline, autoplay_audio
    return LLMCoach, TextToSpeech, VoicePipeline, autoplay_audio


# =========================
# MAIN APP
# =========================

def main():
    st.set_page_config(
        page_icon="🏋️‍♀️",
        page_title="AI Real-time GYM Coach",
        initial_sidebar_state="expanded",
        layout="centered"
    )

    load_css(os.path.join(os.getcwd(), "static", "style.css"))
    inject_local_font(os.path.join(os.getcwd(), "static", "AdobeClean.otf"), "AdobeClean")

    init_db()

    if not render_login_wall():
        return

    initial_session_defaults()

    # =========================
    # VOICE PIPELINE (LAZY LOAD)
    # =========================
    if "voice_pipeline" not in st.session_state:
        try:
            api_key = os.environ.get("GROQ_API_KEY", "")

            if not api_key and hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
                api_key = st.secrets["GROQ_API_KEY"]

            Groq = get_groq()
            LLMCoach, TextToSpeech, VoicePipeline, autoplay_audio = get_coach()

            groq_client = Groq(api_key=api_key)
            llm_coach = LLMCoach(groq_client)
            tts = TextToSpeech()

            st.session_state.voice_pipeline = VoicePipeline(llm_coach, tts)

        except Exception:
            st.session_state.voice_pipeline = None

    workout_started = st.session_state.get("workout_started", False)

    # =========================
    # SIDEBAR
    # =========================
    with st.sidebar:
        st.title("🏋️‍♂️ AI Coach")

        if st.session_state.username:
            st.caption(f"👤 Login as {st.session_state.username}")

        st.divider()
        st.subheader("Workout Plan")

        if not workout_started:
            plan_exercise = st.selectbox("Exercise", options=EXERCISE_OPTIONS, key="plan_exercise")
            plan_sets = st.number_input("Sets", min_value=0, max_value=50, step=1)
            plan_reps = st.number_input("Reps per Set", min_value=0, max_value=50, step=1)

            if st.button("Start Workout"):
                st.session_state.exercise_type = plan_exercise
                st.session_state.target_sets = int(plan_sets)
                st.session_state.reps_per_set = int(plan_reps)
                st.session_state.reps = 0
                st.session_state.workout_started = True

                if st.session_state.voice_pipeline:
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_started",
                        exercise=plan_exercise,
                        metrics={}
                    )
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result

                st.rerun()

        else:
            st.info("Workout Running...")

            if st.button("End Workout"):
                st.session_state.workout_started = False

                if st.session_state.voice_pipeline:
                    result = st.session_state.voice_pipeline.process_event(
                        event="workout_completed",
                        exercise=st.session_state.exercise_type,
                        metrics={}
                    )
                    if result:
                        st.session_state.audio_to_play, st.session_state.coach_feedback = result

                st.rerun()

    # =========================
    # MAIN AREA
    # =========================

    st.title("AI Real-time GYM Coach")

    if st.session_state.get("audio_to_play"):
        from services.coaching.voice_pipeline import autoplay_audio
        autoplay_audio(st.session_state.audio_to_play)

    if st.session_state.get("coach_feedback"):
        st.success(f"🤖 Coach: {st.session_state.coach_feedback}")

    if not workout_started:
        st.info("Set workout plan and start session.")
    else:
        webrtc_streamer, WebRtcMode = get_webrtc()
        VideoProcessorClass = get_video_processor()

        context = webrtc_streamer(
            key="exercise-analysis",
            mode=WebRtcMode.SENDRECV,
            video_processor_factory=VideoProcessorClass,
            rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True
        )

        if context.state.playing:
            time.sleep(0.2)
            st.rerun()

        inject_webrtc_styles()

    # =========================
    # HISTORY
    # =========================

    st.divider()
    st.subheader("Workout History")

    user_id = st.session_state.get("user_id", 0)

    history_rows = get_users_exercises(user_id)

    df = pd.DataFrame(history_rows)

    if not df.empty:
        st.dataframe(df)
    else:
        st.info("No workout history found.")


if __name__ == "__main__":
    main()