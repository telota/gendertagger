"""
Streamlit-based Gender Annotation Web Application

A gamified interface for annotating gender in TEI-XML person registers.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import time
from datetime import datetime
import json
import sys

# Add src directory to path for imports
# This file is at: src/gender_project/ui/app.py
# We need to add: src/ to the path
current_file = Path(__file__).resolve()
src_path = (
    current_file.parent.parent.parent
)  # Go up 3 levels: ui -> gender_project -> src
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from gender_project.classification.gender import (
    get_available_classifiers,
    run_classifiers,
    classify_dataframe,
    OllamaLLMClassifier,
)
from gender_project.data.extract import (
    load_person_register_from_directory,
    export_enriched_tei,
)
from gender_project.ui.database import Database, init_database


# Page configuration
st.set_page_config(
    page_title="TEI Gender Annotator",
    page_icon="⚧",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state():
    """Initialize session state variables."""
    if "db" not in st.session_state:
        st.session_state.db = init_database()

    if "current_mode" not in st.session_state:
        st.session_state.current_mode = "browse"

    if "game_score" not in st.session_state:
        st.session_state.game_score = 0

    if "game_streak" not in st.session_state:
        st.session_state.game_streak = 0

    if "game_start_time" not in st.session_state:
        st.session_state.game_start_time = None

    if "current_question_idx" not in st.session_state:
        st.session_state.current_question_idx = 0

    if "game_questions" not in st.session_state:
        st.session_state.game_questions = []

    if "player_name" not in st.session_state:
        st.session_state.player_name = "Anonymous"

    if "classifiers" not in st.session_state:
        with st.spinner("Loading classifiers..."):
            st.session_state.classifiers = get_available_classifiers()


def sidebar_navigation():
    """Render sidebar navigation."""
    st.sidebar.title("⚧ TEI Gender Annotator")
    st.sidebar.markdown("---")

    mode = st.sidebar.radio(
        "Navigation",
        ["Browse & Annotate", "Game Mode", "Statistics", "Leaderboard", "Settings"],
        key="nav_radio",
    )

    mode_map = {
        "Browse & Annotate": "browse",
        "Game Mode": "game",
        "Statistics": "stats",
        "Leaderboard": "leaderboard",
        "Settings": "settings",
    }

    st.session_state.current_mode = mode_map[mode]

    st.sidebar.markdown("---")

    # Show statistics in sidebar
    stats = st.session_state.db.get_annotation_statistics()

    st.sidebar.metric("Total Persons", stats["total_persons"])
    st.sidebar.metric("Annotated", stats["annotated_count"])

    if stats["total_persons"] > 0:
        progress = stats["annotated_count"] / stats["total_persons"]
        st.sidebar.progress(progress)
        st.sidebar.caption(f"{progress*100:.1f}% Complete")


def render_person_card(person: dict, show_classifiers: bool = True):
    """Render a person information card."""
    col1, col2 = st.columns([2, 1])

    with col1:
        # Display name - handle empty forename/surname
        forename = person.get("forename", "") or ""
        surname = person.get("surname", "") or ""
        name = person.get("name", "") or ""

        # Use full name if available, otherwise combine forename/surname
        if name:
            display_name = name
        else:
            display_name = f"{forename} {surname}".strip()

        if not display_name:
            display_name = person.get("xml_id", "Unknown")

        st.subheader(display_name)

        if person.get("birth_date") or person.get("death_date"):
            dates = []
            if person.get("birth_date"):
                dates.append(f"*{person['birth_date']}")
            if person.get("death_date"):
                dates.append(f"†{person['death_date']}")
            st.caption(" - ".join(dates))

        if person.get("notes"):
            with st.expander("📝 Notes"):
                st.write(person["notes"])

        if person.get("gnd_id"):
            st.caption(f"🔗 GND: {person['gnd_id']}")

    with col2:
        if person.get("sex"):
            sex_map = {
                "M": "♂️ Male",
                "F": "♀️ Female",
                "O": "🏢 Institution",
                "": "❓ Unknown",
            }
            st.info(f"Current: {sex_map.get(person['sex'], '❓ Unknown')}")

    # Show classifier predictions
    if show_classifiers and st.session_state.classifiers:
        st.markdown("#### 🤖 Classifier Predictions")

        # Run classifiers
        results = run_classifiers(person, st.session_state.classifiers)

        cols = st.columns(len(results))
        for idx, (clf_name, (gender, confidence)) in enumerate(results.items()):
            with cols[idx]:
                gender_icon = {
                    "male": "♂️",
                    "female": "♀️",
                    "unknown": "❓",
                    "institution": "🏢",
                }
                st.metric(clf_name, gender_icon.get(gender, "❓"), f"{confidence:.0%}")


def browse_mode():
    """Browse and annotate mode."""
    st.title("Browse & Annotate")

    # Compact filters in one row
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

    with col1:
        filter_status = st.selectbox(
            "Status",
            ["All", "Unannotated", "Annotated", "Uncertain"],
            label_visibility="collapsed",
            placeholder="Filter by status",
        )

    with col2:
        filter_gender = st.selectbox(
            "Gender",
            ["All", "Male", "Female", "Unknown", "Institution"],
            label_visibility="collapsed",
            placeholder="Filter by gender",
        )

    with col3:
        search = st.text_input(
            "Search", label_visibility="collapsed", placeholder="Search by name"
        )

    with col4:
        items_per_page = st.selectbox(
            "Per page", [10, 25, 50, 100], index=0, label_visibility="collapsed"
        )

    # Get persons
    persons_df = st.session_state.db.get_persons_with_annotations()

    # Apply filters
    if filter_status == "Unannotated":
        persons_df = persons_df[persons_df["human_gender"].isna()]
    elif filter_status == "Annotated":
        persons_df = persons_df[persons_df["human_gender"].notna()]
    elif filter_status == "Uncertain":
        persons_df = persons_df[persons_df["is_uncertain"]]

    if filter_gender != "All":
        gender_map = {
            "Male": "male",
            "Female": "female",
            "Unknown": "unknown",
            "Institution": "institution",
        }
        persons_df = persons_df[persons_df["human_gender"] == gender_map[filter_gender]]

    if search:
        mask = (
            persons_df["name"].str.contains(search, case=False, na=False)
            | persons_df["forename"].str.contains(search, case=False, na=False)
            | persons_df["surname"].str.contains(search, case=False, na=False)
        )
        persons_df = persons_df[mask]

    # Compact pagination
    total_pages = max(1, (len(persons_df) - 1) // items_per_page + 1)

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption(f"Showing {len(persons_df)} persons")
    with col_b:
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=1,
            label_visibility="collapsed",
        )

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page

    page_df = persons_df.iloc[start_idx:end_idx]

    # Display persons compactly
    for idx, person in page_df.iterrows():
        st.markdown("---")

        # Compact person info
        name = (
            person.get("name", "")
            or f"{person.get('forename', '')} {person.get('surname', '')}".strip()
            or person.get("xml_id", "Unknown")
        )

        # Add gender icon and colored background if annotated
        if person.get("human_gender"):
            sex_map = {
                "male": ("♂️", "#d4e6f1"),  # light blue
                "female": ("♀️", "#f9e6f0"),  # light pink
                "institution": ("🏢", "#e8f5e9"),  # light green
                "unknown": ("❓", "#f5f5f5"),  # light gray
            }
            icon, bg_color = sex_map.get(person["human_gender"], ("❓", "#f5f5f5"))
            st.markdown(
                f'<div style="background-color: {bg_color}; padding: 8px; border-radius: 5px; display: inline-block;">'
                f"{icon} <strong>{name}</strong></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"**{name}**")

        # Compact metadata on one line
        meta = []
        if person.get("birth_date"):
            meta.append(f"*{person['birth_date']}")
        if person.get("death_date"):
            meta.append(f"†{person['death_date']}")
        if person.get("gnd_id"):
            meta.append("🔗 GND")
        if meta:
            st.caption(" | ".join(meta))

        if person.get("notes"):
            st.caption(f"📝 {person['notes']}")

        # Initialize classifier display state
        classify_key = f"show_classifiers_{idx}"
        if classify_key not in st.session_state:
            st.session_state[classify_key] = False

        # Action buttons
        col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 1, 1])

        with col1:
            if st.button("♂️ Male", key=f"male_{idx}"):
                st.session_state.db.save_annotation(
                    person["xml_id"],
                    "male",
                    st.session_state.player_name,
                    is_uncertain=False,
                )
                st.rerun()

        with col2:
            if st.button("♀️ Female", key=f"female_{idx}"):
                st.session_state.db.save_annotation(
                    person["xml_id"],
                    "female",
                    st.session_state.player_name,
                    is_uncertain=False,
                )
                st.rerun()

        with col3:
            if st.button("🏢 Institution", key=f"inst_{idx}"):
                st.session_state.db.save_annotation(
                    person["xml_id"],
                    "institution",
                    st.session_state.player_name,
                    is_uncertain=False,
                )
                st.rerun()

        with col4:
            if st.button("❓ Uncertain", key=f"unc_{idx}"):
                st.session_state.db.save_annotation(
                    person["xml_id"],
                    "unknown",
                    st.session_state.player_name,
                    is_uncertain=True,
                )
                st.rerun()

        with col5:
            if st.button("🤖", key=f"classify_{idx}", help="Run classifiers"):
                st.session_state[classify_key] = not st.session_state[classify_key]
                st.rerun()

        with col6:
            if person.get("human_gender"):
                if st.button("🗑️", key=f"del_{idx}"):
                    st.session_state.db.delete_annotation(person["xml_id"])
                    st.rerun()

        # Check if classifier results exist in database
        stored_results = st.session_state.db.get_classifier_results(person["xml_id"])

        # Show classifier results if they exist OR if user clicked the classify button
        if not stored_results.empty:
            # Display stored results from database
            st.markdown("##### 🤖 Classifier Predictions")
            cols = st.columns(min(len(stored_results), 6))
            for clf_idx, row in stored_results.iterrows():
                with cols[clf_idx % 6]:
                    gender_icon = {
                        "male": "♂️",
                        "female": "♀️",
                        "unknown": "❓",
                        "institution": "🏢",
                    }
                    icon = gender_icon.get(row["predicted_gender"], "❓")
                    st.caption(
                        f"**{row['classifier_name']}**  \n{icon} {row['confidence']:.0%}"
                    )
        elif st.session_state.get(classify_key, False):
            # Run classifiers if button was clicked and no stored results
            results = run_classifiers(person.to_dict(), st.session_state.classifiers)

            # Save results to database
            for clf_name, (gender, confidence) in results.items():
                st.session_state.db.save_classifier_result(
                    person["xml_id"], clf_name, gender, confidence
                )

            # Display in compact grid
            st.markdown("##### 🤖 Classifier Predictions")
            cols = st.columns(min(len(results), 6))
            for clf_idx, (clf_name, (gender, confidence)) in enumerate(results.items()):
                with cols[clf_idx % 6]:
                    gender_icon = {
                        "male": "♂️",
                        "female": "♀️",
                        "unknown": "❓",
                        "institution": "🏢",
                    }
                    icon = gender_icon.get(gender, "❓")
                    st.caption(f"**{clf_name}**  \n{icon} {confidence:.0%}")

    # Bottom pagination controls
    st.markdown("---")
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.caption(f"Page {page} of {total_pages}")
    with col_b:
        bottom_page = st.number_input(
            "Go to page",
            min_value=1,
            max_value=total_pages,
            value=page,
            key="bottom_page_nav",
            label_visibility="collapsed",
        )
        if bottom_page != page:
            st.rerun()


def game_mode():
    """Gamified annotation mode."""
    st.title("🎮 Game Mode")

    # Player name input
    col1, col2 = st.columns([3, 1])
    with col1:
        player_name = st.text_input("Your name", value=st.session_state.player_name)
        st.session_state.player_name = player_name

    with col2:
        difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"])

    # Start game
    if not st.session_state.game_questions:
        if st.button("🚀 Start New Game", type="primary"):
            # Get unannotated persons
            persons_df = st.session_state.db.get_persons_with_annotations()
            unannotated = persons_df[persons_df["human_gender"].isna()]

            if len(unannotated) == 0:
                st.warning("No unannotated persons available!")
                return

            # Sample questions based on difficulty
            n_questions = {"Easy": 10, "Medium": 20, "Hard": 50}[difficulty]
            n_questions = min(n_questions, len(unannotated))

            st.session_state.game_questions = unannotated.sample(n_questions).to_dict(
                "records"
            )
            st.session_state.current_question_idx = 0
            st.session_state.game_score = 0
            st.session_state.game_streak = 0
            st.session_state.game_total_time = 0  # Track cumulative time
            st.session_state.game_completed = False
            st.rerun()

    # Game in progress
    if st.session_state.game_questions:
        questions = st.session_state.game_questions
        idx = st.session_state.current_question_idx

        # Check if game is complete
        if idx >= len(questions):
            # Only save to leaderboard once
            if not st.session_state.get("game_completed", False):
                st.balloons()
                total_time = st.session_state.game_total_time
                final_score = st.session_state.game_score

                # Save to leaderboard
                st.session_state.db.add_leaderboard_entry(
                    player_name=st.session_state.player_name,
                    score=final_score,
                    time_seconds=total_time,
                    questions_answered=len(questions),
                )
                st.session_state.game_completed = True

            # Show completion screen
            st.success("🎉 Game Complete!")

            total_time = st.session_state.game_total_time
            final_score = st.session_state.game_score

            st.metric("Final Score", final_score)
            st.metric("Time", f"{total_time:.1f}s")
            st.metric("Avg Speed", f"{total_time/len(questions):.1f}s per person")

            if st.button("🔄 Play Again"):
                st.session_state.game_questions = []
                st.session_state.game_completed = False
                st.rerun()

            return

        # Current question
        person = questions[idx]

        # Initialize answer tracking for this question
        answer_key = f"game_answer_{idx}"
        answer_time_key = f"game_answer_time_{idx}"
        question_start_key = f"game_question_start_{idx}"

        if answer_key not in st.session_state:
            st.session_state[answer_key] = None
        if question_start_key not in st.session_state:
            # Record when this specific question started (only set once per question)
            st.session_state[question_start_key] = time.time()

        # Calculate elapsed time for THIS question only
        if st.session_state.get(answer_key) is not None:
            # Answer was given - show frozen time
            if answer_time_key in st.session_state:
                elapsed = st.session_state[answer_time_key]
            else:
                # Shouldn't happen, but fallback
                elapsed = 0
        else:
            # No answer yet - time is running
            elapsed = time.time() - st.session_state[question_start_key]
            # Auto-refresh to update timer, but add a small delay to prevent immediate loop
            # Only rerun if enough time has passed since last rerun
            last_rerun_key = f"last_rerun_{idx}"
            current_time = time.time()
            last_rerun = st.session_state.get(last_rerun_key, 0)

            if current_time - last_rerun > 0.5:  # Only rerun every 0.5 seconds
                st.session_state[last_rerun_key] = current_time
                time.sleep(0.1)
                st.rerun()

        # Progress bar and score in one compact row
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            progress = idx / len(questions)
            st.progress(progress)
            st.caption(f"Question {idx+1}/{len(questions)}")
        with col2:
            st.metric("Score", st.session_state.game_score, label_visibility="visible")
        with col3:
            st.metric(
                "Streak",
                f"🔥{st.session_state.game_streak}",
                label_visibility="visible",
            )
        with col4:
            st.metric("Time", f"{elapsed:.0f}s", label_visibility="visible")

        st.markdown("---")

        # Show person info compactly (no expanders, minimal spacing)
        name = (
            person.get("name", "")
            or f"{person.get('forename', '')} {person.get('surname', '')}".strip()
            or person.get("xml_id", "Unknown")
        )

        col_left, col_right = st.columns([3, 1])
        with col_left:
            st.markdown(f"### {name}")
            dates = []
            if person.get("birth_date"):
                dates.append(f"*{person['birth_date']}")
            if person.get("death_date"):
                dates.append(f"†{person['death_date']}")
            if dates:
                st.caption(" - ".join(dates))
            if person.get("notes"):
                st.caption(f"📝 {person['notes']}")
        with col_right:
            if person.get("gnd_id"):
                st.caption("🔗 GND")

        # Answer buttons (disabled after answer is given)
        st.markdown("#### Your Answer")
        col1, col2, col3, col4 = st.columns(4)

        buttons_disabled = st.session_state.get(answer_key) is not None

        # Define callbacks for each answer button
        def answer_callback(gender_value):
            """Handle answer button click."""

            def callback():
                # Calculate elapsed time at moment of click
                elapsed = 0.0  # Default value
                if question_start_key in st.session_state:
                    elapsed = time.time() - st.session_state[question_start_key]
                    st.session_state[answer_time_key] = elapsed

                # Save the answer
                st.session_state[answer_key] = gender_value

                # Save annotation
                st.session_state.db.save_annotation(
                    person["xml_id"],
                    gender_value,
                    st.session_state.player_name,
                    is_uncertain=False,
                )

                # Update score
                base_points = 10
                streak_bonus = st.session_state.game_streak * 2
                time_bonus = max(0, 10 - int(elapsed / len(questions)))

                points = base_points + streak_bonus + time_bonus
                st.session_state.game_score += points
                st.session_state.game_streak += 1

            return callback

        with col1:
            st.button(
                "♂️ Male",
                key=f"game_male_{idx}",
                disabled=buttons_disabled,
                on_click=answer_callback("male"),
                use_container_width=True,
            )

        with col2:
            st.button(
                "♀️ Female",
                key=f"game_female_{idx}",
                disabled=buttons_disabled,
                on_click=answer_callback("female"),
                use_container_width=True,
            )

        with col3:
            st.button(
                "🏢 Institution",
                key=f"game_inst_{idx}",
                disabled=buttons_disabled,
                on_click=answer_callback("institution"),
                use_container_width=True,
            )

        with col4:

            def skip_callback():
                """Handle skipping a question."""
                # Add time for skipped question
                current_time = time.time() - st.session_state[question_start_key]
                st.session_state.game_total_time += current_time

                st.session_state.current_question_idx += 1
                st.session_state.game_streak = 0
                # Clear the answer and tracking for this question
                last_rerun_key = f"last_rerun_{idx}"
                if answer_key in st.session_state:
                    del st.session_state[answer_key]
                if answer_time_key in st.session_state:
                    del st.session_state[answer_time_key]
                if question_start_key in st.session_state:
                    del st.session_state[question_start_key]
                if last_rerun_key in st.session_state:
                    del st.session_state[last_rerun_key]

            st.button(
                "⏭️ Skip",
                key=f"game_skip_{idx}",
                disabled=buttons_disabled,
                on_click=skip_callback,
                use_container_width=True,
            )

        # Show classifier results AFTER user has answered (compact view)
        if st.session_state.get(answer_key):
            st.markdown("---")
            st.markdown("**🤖 Classifier Predictions**")

            with st.spinner("Running classifiers..."):
                # Run classifiers
                results = run_classifiers(person, st.session_state.classifiers)

            # Show classifiers in a compact grid
            cols = st.columns(min(len(results), 5))  # Max 5 per row
            for clf_idx, (clf_name, (gender, confidence)) in enumerate(results.items()):
                with cols[clf_idx % 5]:
                    gender_icon = {
                        "male": "♂️",
                        "female": "♀️",
                        "unknown": "❓",
                        "institution": "🏢",
                    }
                    icon = gender_icon.get(gender, "❓")
                    st.markdown(f"**{clf_name}**  \n{icon} {confidence:.0%}")

            # Show continue button prominently
            st.markdown("")  # Small spacing

            # Use callback to ensure state updates happen reliably
            def next_question_callback():
                """Handle advancing to next question."""
                # Add this question's time to total
                if answer_time_key in st.session_state:
                    st.session_state.game_total_time += st.session_state[
                        answer_time_key
                    ]

                st.session_state.current_question_idx += 1
                # Clear the answer and time for this question
                last_rerun_key = f"last_rerun_{idx}"
                if answer_key in st.session_state:
                    del st.session_state[answer_key]
                if answer_time_key in st.session_state:
                    del st.session_state[answer_time_key]
                if question_start_key in st.session_state:
                    del st.session_state[question_start_key]
                if last_rerun_key in st.session_state:
                    del st.session_state[last_rerun_key]

            st.button(
                "➡️ Next Question",
                key=f"game_next_{idx}",
                type="primary",
                on_click=next_question_callback,
                use_container_width=True,
            )


def statistics_mode():
    """Statistics and analytics mode."""
    st.title("📊 Statistics")

    # Overall stats
    stats = st.session_state.db.get_annotation_statistics()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Persons", stats["total_persons"])

    with col2:
        st.metric("Annotated", stats["annotated_count"])

    with col3:
        completion = (
            stats["annotated_count"] / stats["total_persons"] * 100
            if stats["total_persons"] > 0
            else 0
        )
        st.metric("Completion", f"{completion:.1f}%")

    with col4:
        st.metric("Uncertain", stats["uncertain_count"])

    st.markdown("---")

    # Gender distribution
    st.subheader("Gender Distribution")

    persons_df = st.session_state.db.get_persons_with_annotations()
    annotated = persons_df[persons_df["human_gender"].notna()]

    if len(annotated) > 0:
        gender_counts = annotated["human_gender"].value_counts()

        import plotly.express as px

        fig = px.pie(
            values=gender_counts.values,
            names=gender_counts.index,
            title="Annotated Gender Distribution",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No annotations yet")


def leaderboard_mode():
    """Leaderboard mode."""
    st.title("🏆 Leaderboard")

    leaderboard = st.session_state.db.get_leaderboard(limit=10)

    if not leaderboard.empty:
        # Format the display
        leaderboard_display = leaderboard.copy()
        leaderboard_display["avg_time"] = (
            leaderboard_display["time_seconds"]
            / leaderboard_display["questions_answered"]
        )
        leaderboard_display["avg_time"] = leaderboard_display["avg_time"].apply(
            lambda x: f"{x:.1f}s"
        )

        st.dataframe(
            leaderboard_display[
                [
                    "rank",
                    "player_name",
                    "score",
                    "questions_answered",
                    "avg_time",
                    "played_at",
                ]
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No games played yet. Start a game to appear on the leaderboard!")


def settings_mode():
    """Settings and data management mode."""
    st.title("⚙️ Settings")

    st.subheader("📥 Import Data")

    # Import from directory
    data_dir = st.text_input(
        "Person Register Directory", value=str(Path("data/raw/Register/Personen"))
    )

    if st.button("Import Person Register", type="primary"):
        with st.spinner("Loading XML files..."):
            try:
                df = load_person_register_from_directory(Path(data_dir))

                if not df.empty:
                    # Import to database
                    st.session_state.db.import_persons(df)
                    st.success(f"Imported {len(df)} persons!")
                else:
                    st.warning("No persons found in the directory")
            except Exception as e:
                st.error(f"Error importing: {e}")

    st.markdown("---")

    # Export annotations
    st.subheader("📤 Export Annotations")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Download CSV"):
            persons_df = st.session_state.db.get_persons_with_annotations()
            csv = persons_df.to_csv(index=False)

            st.download_button(
                "Download",
                csv,
                file_name=f"annotations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

    with col2:
        if st.button("Download JSON"):
            persons_df = st.session_state.db.get_persons_with_annotations()
            json_str = persons_df.to_json(orient="records", indent=2)

            st.download_button(
                "Download",
                json_str,
                file_name=f"annotations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

    st.markdown("---")

    # Classifier settings
    st.subheader("🤖 Classifiers")

    st.write(f"Loaded {len(st.session_state.classifiers)} classifiers:")
    for clf in st.session_state.classifiers:
        st.write(f"- {clf.name}")

    if st.button("Reload Classifiers"):
        with st.spinner("Reloading classifiers..."):
            st.session_state.classifiers = get_available_classifiers()
            st.success("Classifiers reloaded!")

    # LLM Classifier Configuration
    st.markdown("#### Add Ollama LLM Classifier")

    col1, col2 = st.columns(2)
    with col1:
        ollama_model = st.text_input(
            "Ollama Model",
            value="gpt-oss:120b",
            help="Model name (e.g., gpt-oss:120b, llama2:7b)",
        )
    with col2:
        ollama_url = st.text_input(
            "Ollama API URL",
            value="http://localhost:11434/api/generate",
            help="URL of your Ollama API endpoint",
        )

    if st.button("Add LLM Classifier"):
        try:
            from gender_project.classification.gender import OllamaLLMClassifier

            llm_clf = OllamaLLMClassifier(model_name=ollama_model, api_url=ollama_url)

            # Check if it already exists
            existing_names = [clf.name for clf in st.session_state.classifiers]
            if llm_clf.name not in existing_names:
                st.session_state.classifiers.append(llm_clf)
                st.success(f"Added LLM classifier: {llm_clf.name}")
            else:
                st.warning(f"Classifier {llm_clf.name} already exists")
        except Exception as e:
            st.error(f"Error adding LLM classifier: {e}")

    st.markdown("---")

    # Database stats
    st.subheader("💾 Database")

    stats = st.session_state.db.get_annotation_statistics()
    st.json(stats)


def main():
    """Main application entry point."""
    init_session_state()
    sidebar_navigation()

    # Route to correct mode
    if st.session_state.current_mode == "browse":
        browse_mode()
    elif st.session_state.current_mode == "game":
        game_mode()
    elif st.session_state.current_mode == "stats":
        statistics_mode()
    elif st.session_state.current_mode == "leaderboard":
        leaderboard_mode()
    elif st.session_state.current_mode == "settings":
        settings_mode()


if __name__ == "__main__":
    main()
