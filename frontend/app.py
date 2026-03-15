import datetime
import os
from typing import Optional
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


BACKEND_URL = os.getenv("WORDLE_BACKEND_URL", "http://localhost:8000")

# Timezones for "today" and default dates (server may be UTC; user's date can differ)
TIMEZONES = [
    "UTC",
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "Europe/London",
    "Europe/Paris",
    "Asia/Kolkata",
    "Asia/Tokyo",
    "Australia/Sydney",
]


def get_user_today(user: Optional[dict]) -> datetime.date:
    """Return 'today' in the user's timezone so deployed app matches local date."""
    tz_name = (user or {}).get("timezone") or "UTC"
    try:
        return datetime.datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return datetime.datetime.now(ZoneInfo("UTC")).date()


def api_post(path: str, json: dict) -> tuple[Optional[dict], Optional[str]]:
    """Make POST request, return (data, error_message)."""
    try:
        resp = requests.post(f"{BACKEND_URL}{path}", json=json, timeout=5)
        resp.raise_for_status()
        return resp.json(), None
    except requests.exceptions.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return None, detail
    except Exception as exc:  # noqa: BLE001
        return None, f"Request failed: {exc}"


def api_get(path: str, params: Optional[dict] = None) -> Optional[dict]:
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Request failed: {exc}")
        return None


def api_put(path: str, json: dict) -> tuple[Optional[dict], Optional[str]]:
    """Make PUT request, return (data, error_message)."""
    try:
        resp = requests.put(f"{BACKEND_URL}{path}", json=json, timeout=5)
        resp.raise_for_status()
        return (resp.json() if resp.content else {}), None
    except requests.exceptions.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return None, detail
    except Exception as exc:  # noqa: BLE001
        return None, f"Request failed: {exc}"


def ensure_session_state():
    if "user" not in st.session_state:
        st.session_state["user"] = None
    if "auth_mode" not in st.session_state:
        st.session_state["auth_mode"] = "login"
    if "editing_field" not in st.session_state:
        st.session_state["editing_field"] = None
    if "show_password_dialog" not in st.session_state:
        st.session_state["show_password_dialog"] = False


def show_login_page():
    st.title("Wordle Tracker")

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        show_login_form()

    with tab_register:
        show_register_form()


def show_login_form():
    st.subheader("Welcome back!")

    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login", type="primary", key="login_btn"):
        if not username.strip():
            st.warning("Please enter a username.")
            return
        if not password:
            st.warning("Please enter a password.")
            return

        data, error = api_post("/login", {
            "username": username.strip(),
            "password": password,
        })
        if error:
            st.error(error)
        elif data:
            st.session_state["user"] = data
            display = data.get("pet_name") or data.get("username", "")
            st.success(f"Logged in as {display}")
            st.rerun()


def _display_name(obj: dict) -> str:
    """Return pet_name for UI display, fallback to username."""
    return (obj.get("pet_name") or obj.get("username") or "").strip()


def show_register_form():
    st.subheader("Create an account")

    username = st.text_input("Username", key="register_username", help="Used for login")
    first_name = st.text_input("First name", key="register_first_name")
    last_name = st.text_input("Last name", key="register_last_name")
    pet_name = st.text_input("Pet name", key="register_pet_name", help="Shown on leaderboards and analytics")
    password = st.text_input("Password", type="password", key="register_password")
    confirm_password = st.text_input("Confirm Password", type="password", key="register_confirm")

    if st.button("Register", type="primary", key="register_btn"):
        if not username.strip():
            st.warning("Please enter a username.")
            return
        if not first_name.strip():
            st.warning("Please enter your first name.")
            return
        if not last_name.strip():
            st.warning("Please enter your last name.")
            return
        if not pet_name.strip():
            st.warning("Please enter a pet name.")
            return
        if not password:
            st.warning("Please enter a password.")
            return
        if len(password) < 4:
            st.warning("Password must be at least 4 characters.")
            return
        if password != confirm_password:
            st.warning("Passwords do not match.")
            return

        data, error = api_post("/register", {
            "username": username.strip(),
            "password": password,
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
            "pet_name": pet_name.strip(),
        })
        if error:
            st.error(error)
        elif data:
            st.session_state["user"] = data
            st.success(f"Account created! Logged in as {_display_name(data)}")
            st.rerun()


def show_main_app():
    user = st.session_state["user"]
    st.sidebar.markdown(f"**Logged in as:** {_display_name(user)}")
    if st.sidebar.button("Logout"):
        st.session_state["user"] = None
        st.rerun()

    st.title("Wordle Tracker")

    tab_today, tab_log, tab_analytics, tab_settings = st.tabs([
        "📋 Today's Status",
        "✏️ Log Result",
        "📊 Analytics",
        "⚙️ Settings",
    ])

    with tab_today:
        show_today_tab(user)

    with tab_log:
        show_log_tab(user)

    with tab_analytics:
        show_analytics_tab(user)

    with tab_settings:
        show_settings_tab(user)


def show_today_tab(user: dict):
    st.subheader("📋 Today's Status")

    user_today = get_user_today(user)
    today_data = api_get("/results/today", params={"date": user_today.isoformat()})
    if not today_data:
        st.info("No users registered yet.")
        return

    cols = st.columns(len(today_data))
    for idx, status in enumerate(today_data):
        with cols[idx]:
            st.markdown(f"### {_display_name(status)}")
            if status["has_entry"]:
                result = status["result"]
                if result["completed"]:
                    st.success(f"✅ Solved in {result['attempts']} attempts")
                else:
                    st.error("❌ Did not complete")
                st.metric("Score", result["score"])
            else:
                st.warning("TBD")
                st.caption("⏳ No entry for today yet")


def show_log_tab(user: dict):
    st.subheader("✏️ Log a Wordle result")

    user_today = get_user_today(user)
    date_value = st.date_input("Date", value=user_today)

    attempts = st.number_input("Number of attempts (1-6)", min_value=1, max_value=6, value=4)

    if st.button("Save Result", type="primary"):
        payload = {
            "username": user["username"],
            "date": date_value.isoformat(),
            "attempts": int(attempts),
            "completed": True,
        }
        data, error = api_post("/results", payload)
        if error:
            st.error(error)
        elif data:
            st.success(
                f"Saved result for {data['date']}: "
                f"{data['attempts']} attempts, "
                f"score {data['score']}"
            )


def _profile_row(label: str, field_key: str, current_value: str):
    """One row: label, then either display + pencil or text_input + floppy. Returns True if Save was clicked."""
    editing = st.session_state.get("editing_field") == field_key
    col_label, col_value, col_btn = st.columns([2, 4, 1])
    with col_label:
        st.markdown(f"**{label}**")
    with col_value:
        if editing:
            st.text_input(
                label,
                value=current_value or "",
                key=f"edit_{field_key}",
                label_visibility="collapsed",
            )
        else:
            st.text(current_value or "—")
    with col_btn:
        if editing:
            return st.button("💾", key=f"save_{field_key}", help="Save")
        else:
            if st.button("✏️", key=f"pencil_{field_key}", help="Edit"):
                st.session_state["editing_field"] = field_key
                st.rerun()
            return False


@st.dialog("Change Password")
def change_password_dialog(username: str):
    st.caption("Enter your current password and choose a new one.")
    old_password = st.text_input("Current password", type="password", key="pw_old")
    new_password = st.text_input("New password", type="password", key="pw_new")
    confirm_password = st.text_input("Confirm new password", type="password", key="pw_confirm")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save password", type="primary", key="pw_save"):
            if not old_password or not new_password or not confirm_password:
                st.error("Please fill all fields.")
            elif new_password != confirm_password:
                st.error("New password and confirmation do not match.")
            elif len(new_password) < 4:
                st.error("New password must be at least 4 characters.")
            else:
                _, err = api_post("/users/change-password", {
                    "username": username,
                    "old_password": old_password,
                    "new_password": new_password,
                })
                if err:
                    st.error(err)
                else:
                    st.success("Password saved successfully.")
                    st.session_state["show_password_dialog"] = False
                    st.rerun()
    with col2:
        if st.button("Cancel", key="pw_cancel"):
            st.session_state["show_password_dialog"] = False
            st.rerun()


def show_settings_tab(user: dict):
    st.subheader("⚙️ Settings")

    if st.session_state.get("show_password_dialog"):
        change_password_dialog(user["username"])
        return

    st.markdown("Update your profile. Click ✏️ to edit, then 💾 to save.")

    current = user
    first_name = (current.get("first_name") or "").strip()
    last_name = (current.get("last_name") or "").strip()
    pet_name = (current.get("pet_name") or "").strip()
    username = (current.get("username") or "").strip()

    st.session_state.setdefault("editing_field", None)

    # Render all rows first so all widgets are in the same run
    clicked_first = _profile_row("First name", "first_name", first_name)
    clicked_last = _profile_row("Last name", "last_name", last_name)
    clicked_pet = _profile_row("Pet name", "pet_name", pet_name)
    clicked_username = _profile_row("Username", "username", username)

    st.markdown("**Timezone** (for \"today\" and default dates when deployed)")
    current_tz = (current.get("timezone") or "UTC").strip() or "UTC"
    tz_index = next((i for i, t in enumerate(TIMEZONES) if t == current_tz), 0)
    new_tz = st.selectbox(
        "Choose your timezone",
        options=TIMEZONES,
        index=tz_index,
        key="settings_timezone",
        label_visibility="collapsed",
    )
    if st.button("Save timezone", key="save_tz_btn") and new_tz != current_tz:
        data, err = api_put("/users/profile", {"username": user["username"], "timezone": new_tz})
        if err:
            st.error(err)
        else:
            st.session_state["user"] = data
            st.success("Timezone updated.")
            st.rerun()

    if clicked_first:
        val = (st.session_state.get("edit_first_name") or "").strip()
        data, err = api_put("/users/profile", {"username": user["username"], "first_name": val or first_name})
        if err:
            st.error(err)
        else:
            st.session_state["user"] = data
            st.session_state["editing_field"] = None
            st.success("First name updated.")
            st.rerun()

    if clicked_last:
        val = (st.session_state.get("edit_last_name") or "").strip()
        data, err = api_put("/users/profile", {"username": user["username"], "last_name": val or last_name})
        if err:
            st.error(err)
        else:
            st.session_state["user"] = data
            st.session_state["editing_field"] = None
            st.success("Last name updated.")
            st.rerun()

    if clicked_pet:
        val = (st.session_state.get("edit_pet_name") or "").strip()
        data, err = api_put("/users/profile", {"username": user["username"], "pet_name": val or pet_name})
        if err:
            st.error(err)
        else:
            st.session_state["user"] = data
            st.session_state["editing_field"] = None
            st.success("Pet name updated.")
            st.rerun()

    if clicked_username:
        val = (st.session_state.get("edit_username") or "").strip()
        if not val:
            st.error("Username cannot be empty.")
        else:
            data, err = api_put("/users/profile", {"username": user["username"], "new_username": val})
            if err:
                st.error(err)
            else:
                st.session_state["user"] = data
                st.session_state["editing_field"] = None
                st.success("Username updated.")
                st.rerun()

    st.markdown("---")
    st.markdown("**Password**")
    if st.button("Change Password", key="open_pw_dialog"):
        st.session_state["show_password_dialog"] = True
        st.rerun()


def show_analytics_tab(user: dict):
    st.subheader("📊 Analytics Dashboard")

    user_today = get_user_today(user)
    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox(
            "Period",
            options=["day", "week", "month", "year"],
            index=1,
            format_func=lambda v: v.capitalize(),
            key="analytics_period",
        )
    with col2:
        reference_date = st.date_input(
            "Reference date",
            value=user_today,
            key="analytics_date",
        )

    params = {
        "period": period,
        "reference_date": reference_date.isoformat(),
    }
    data = api_get("/analytics", params=params)

    if not data:
        return

    st.markdown(f"**Period:** {data['period_start']} to {data['period_end']}")

    show_winner_banner(data)

    if period in ("week", "month", "year"):
        show_streak_section(data)

    if not data["daily_scores"]:
        st.info("No results recorded for this period yet.")
        return

    show_head_to_head(data)
    show_score_timeline(data)
    show_user_stats_comparison(data)
    show_attempt_distribution(data)


def show_winner_banner(data: dict):
    winner = data.get("winner")
    if winner:
        st.success(f"**🏆 {data['period'].capitalize()} Winner: {winner}**")
    elif data["user_stats"]:
        st.info("**🤝 It's a tie!**")


def show_streak_section(data: dict):
    """Show current streak per user (only for week/month/year)."""
    st.markdown("### 🔥 Streak")
    user_stats = data.get("user_stats", [])
    streak_users = [s for s in user_stats if s.get("streak") is not None]
    if not streak_users:
        st.caption("No streak data for this period.")
        return
    cols = st.columns(len(streak_users))
    for idx, stats in enumerate(streak_users):
        with cols[idx]:
            streak = stats["streak"]
            label = f"{streak} day streak" if streak != 0 else "No streak"
            st.metric(_display_name(stats), label)
            st.caption("🔥")


def show_head_to_head(data: dict):
    h2h = data.get("head_to_head")
    if not h2h:
        return

    st.markdown("### ⚔️ Head-to-Head Record")

    total_games = h2h["user1_wins"] + h2h["user2_wins"] + h2h["ties"]
    if total_games == 0:
        st.info("No head-to-head games yet in this period.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(h2h["user1"], f"{h2h['user1_wins']} wins")
    with col2:
        st.metric("Ties", h2h["ties"])
    with col3:
        st.metric(h2h["user2"], f"{h2h['user2_wins']} wins")

    fig = go.Figure(data=[
        go.Bar(
            x=[h2h["user1"], "Ties", h2h["user2"]],
            y=[h2h["user1_wins"], h2h["ties"], h2h["user2_wins"]],
            marker_color=["#636EFA", "#AB63FA", "#EF553B"],
            text=[h2h["user1_wins"], h2h["ties"], h2h["user2_wins"]],
            textposition="auto",
            textfont=dict(color="#1a1a1a", size=14),
        )
    ])
    fig.update_layout(
        title="Head-to-Head Results",
        yaxis_title="Days Won",
        showlegend=False,
        height=300,
    )
    st.plotly_chart(fig, width="stretch")


def show_score_timeline(data: dict):
    st.markdown("### 📈 Score Timeline")

    daily_scores = data["daily_scores"]
    if not daily_scores:
        return

    dates = []
    scores_by_user = {}
    for entry in daily_scores:
        name = _display_name(entry)
        if name not in scores_by_user:
            scores_by_user[name] = {"dates": [], "scores": []}
        scores_by_user[name]["dates"].append(entry["date"])
        scores_by_user[name]["scores"].append(entry["score"])

    fig = go.Figure()
    colors = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA"]
    for idx, (name, values) in enumerate(scores_by_user.items()):
        fig.add_trace(go.Scatter(
            x=values["dates"],
            y=values["scores"],
            mode="lines+markers",
            name=name,
            line=dict(color=colors[idx % len(colors)], width=3),
            marker=dict(size=10),
        ))

    fig.update_layout(
        title="Daily Scores Over Time",
        xaxis_title="Date",
        yaxis_title="Score",
        hovermode="x unified",
        height=400,
    )
    st.plotly_chart(fig, width="stretch")


def show_user_stats_comparison(data: dict):
    st.markdown("### 📉 Performance Comparison")

    user_stats = data["user_stats"]
    if not user_stats:
        return

    col1, col2 = st.columns(2)

    with col1:
        names = [_display_name(s) for s in user_stats]
        avg_attempts = [s["avg_attempts"] for s in user_stats]

        fig = go.Figure(data=[
            go.Bar(
                x=names,
                y=avg_attempts,
                marker_color=["#636EFA", "#EF553B"][:len(names)],
                text=[f"{a:.1f}" for a in avg_attempts],
                textposition="auto",
                textfont=dict(color="#1a1a1a", size=14),
            )
        ])
        fig.update_layout(
            title="Average Attempts",
            yaxis_title="Attempts",
            height=300,
        )
        st.plotly_chart(fig, width="stretch")

    with col2:
        completion_rates = [s["completion_rate"] for s in user_stats]

        fig = go.Figure(data=[
            go.Bar(
                x=names,
                y=completion_rates,
                marker_color=["#636EFA", "#EF553B"][:len(names)],
                text=[f"{r:.0f}%" for r in completion_rates],
                textposition="auto",
                textfont=dict(color="#1a1a1a", size=14),
            )
        ])
        fig.update_layout(
            title="Completion Rate",
            yaxis_title="Percentage",
            yaxis=dict(range=[0, 100]),
            height=300,
        )
        st.plotly_chart(fig, width="stretch")

    st.markdown("#### Summary Stats")
    stats_table = []
    for s in user_stats:
        stats_table.append({
            "User": _display_name(s),
            "Games": s["games_played"],
            "Total Score": s["total_score"],
            "Avg Attempts": f"{s['avg_attempts']:.2f}",
            "Completion %": f"{s['completion_rate']:.1f}%",
        })
    st.table(stats_table)


def show_attempt_distribution(data: dict):
    st.markdown("### 🎯 Attempt Distribution")

    user_stats = data["user_stats"]
    if not user_stats:
        return

    attempts_labels = ["1", "2", "3", "4", "5", "6"]
    fig = go.Figure()

    colors = ["#636EFA", "#EF553B"]
    for idx, stats in enumerate(user_stats):
        dist = stats["attempt_distribution"]
        values = [dist.get(str(i), dist.get(i, 0)) for i in range(1, 7)]
        fig.add_trace(go.Bar(
            name=_display_name(stats),
            x=attempts_labels,
            y=values,
            marker_color=colors[idx % len(colors)],
        ))

    fig.update_layout(
        title="Games Solved by Number of Attempts",
        xaxis_title="Attempts",
        yaxis_title="Games",
        barmode="group",
        height=400,
    )
    st.plotly_chart(fig, width="stretch")


def main():
    st.set_page_config(page_title="Wordle Tracker", page_icon="🧩", layout="wide")
    ensure_session_state()

    if st.session_state["user"] is None:
        show_login_page()
    else:
        show_main_app()


if __name__ == "__main__":
    main()
