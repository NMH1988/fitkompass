"""The session summary download: a PDF built in memory only when clicked (T5.2, AC-9)."""

from dataclasses import replace
from datetime import date

import streamlit as st

from src import chat, config, export_pdf
from src.chat import TurnResult
from src.tools import coach_clients
from views import chat as chat_view
from views import resources
from views.text import lang, t


def _named(result: TurnResult, names: dict[str, str] | None) -> TurnResult:
    """Return a coach's turn with no link in its answer and each reference as a name (T9.17)."""
    # names is None for a guest, whose answer stays as it is.
    if result.kind != "answer" or names is None:
        return result
    # A coach's chat may hold a client's messages (T11.6a): no URL in the PDF is a link either.
    text = export_pdf.unlinked(result.text)
    # Escaped as Markdown, which the PDF reads back as plain text (a name is a user's own text).
    text = coach_clients.name_references(text, names, chat.escape_markdown)
    return replace(result, text=text)


def summary_download() -> None:
    """Offer the session summary as a PDF, built in memory only when clicked (AC-9)."""
    # Drawn after the main area, so the turn that just ran is in it. The PDF is built from this
    # run's snapshot when the user clicks; Streamlit keeps the bytes in memory, never on disk. It
    # is in the language chosen now (T7.2), bound here: the click may build it outside the run.
    refs = chat_view.client_refs()
    names = refs.names() if refs is not None else None
    turns = tuple(
        (question, _named(result, names))
        for question, result in export_pdf.session_turns(st.session_state["messages"])
    )
    user = st.session_state.get("profile")
    system = st.session_state["units"]
    manifest = resources.manifest()
    current = lang()
    # One date for the file name and the PDF, even if the click comes after midnight.
    today = date.today()

    def build() -> bytes:
        """Build the PDF from this run's session, in this run's language."""
        return export_pdf.build_summary_pdf(turns, user, system, manifest, today, current)

    empty = user is None and not turns
    st.download_button(
        t("pdf.label"),
        data=build,
        file_name=config.PDF_FILE_NAME.format(date=today.isoformat()),
        mime="application/pdf",
        icon=":material/download:",
        # The download needs no rerun of the app.
        on_click="ignore",
        disabled=empty,
        help=t("pdf.empty_help") if empty else t("pdf.help"),
        key="summary_pdf",
        width="stretch",
    )
