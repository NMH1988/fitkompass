"""The texts of the Messages page (T11.4b): a coach-client conversation in real time."""

from src import config

_MAX = config.MESSAGE_MAX_CHARS

EN: dict[str, str] = {
    "messages.intro_coach": (
        "Messages between you and your clients, one conversation per client. They are stored in "
        "this app's data file on this computer, with the sender and the time. A former client "
        "still reads your conversation after your relationship ends, and so do you; neither of "
        "you can send then. Either side's Delete everything (My data) deletes the conversation for "
        "both. Messages are not sent to the AI."
    ),
    "messages.intro_gymer": (
        "Messages between you and your coach. They are stored in this app's data file on this "
        "computer, with the sender and the time. A former coach still reads your conversation "
        "after your relationship ends, and so do you; neither of you can send then. Either side's "
        "Delete everything (My data) deletes the conversation for both. Messages are not sent to "
        "the AI."
    ),
    "messages.made_up_only": "Use made-up data only: do not write real health data.",
    "messages.pick": "Conversation",
    "messages.with": "Conversation with {name}",
    "messages.ended_suffix": "{name} (ended)",
    "messages.ended": (
        "This relationship has ended: you both can still read the conversation, but neither of "
        "you can send."
    ),
    "messages.none_coach": (
        "No conversations yet: a conversation starts when a client connects with your code."
    ),
    "messages.none_gymer": "No conversations yet: connect with a coach on Coach and sharing.",
    "messages.realtime_off": (
        "Real-time messages are off, so you can read this conversation but not send: start the "
        "app with `streamlit run serve.py` instead of `streamlit run app.py`."
    ),
    "messages.wrong_address": (
        "Real-time messages work only when the app is opened at {address}, so you can read this "
        "conversation but not send here."
    ),
    "messages.send": "Send",
    "messages.placeholder": "Write a message (Ctrl+Enter sends)",
    "messages.you": "You",
    "messages.empty": "No messages yet.",
    "messages.connecting": "Connecting…",
    "messages.live": "Connected: new messages appear here.",
    "messages.stopped": "Not connected. Reload the page to try again.",
    "messages.not_sent": "Your message was not sent.",
    "messages.too_long": f"The message is too long: at most {_MAX:,} characters.",
    "messages.other_thread": "New message in another conversation.",
}

DE: dict[str, str] = {
    "messages.intro_coach": (
        "Nachrichten zwischen Ihnen und Ihren Klienten, ein Gespräch je Klient. Sie werden mit "
        "Absender und Uhrzeit in der Datendatei dieser App auf diesem Computer gespeichert. Ein "
        "ehemaliger Klient liest Ihr Gespräch auch nach dem Ende Ihrer Verbindung weiter, ebenso "
        "Sie; senden kann dann keiner von Ihnen. „Alles löschen“ (Meine Daten) löscht das Gespräch "
        "für beide Seiten, egal wer es auslöst. Nachrichten werden nicht an die KI gesendet."
    ),
    "messages.intro_gymer": (
        "Nachrichten zwischen Ihnen und Ihrem Coach. Sie werden mit Absender und Uhrzeit in der "
        "Datendatei dieser App auf diesem Computer gespeichert. Ein ehemaliger Coach liest Ihr "
        "Gespräch auch nach dem Ende Ihrer Verbindung weiter, ebenso Sie; senden kann dann keiner "
        "von Ihnen. „Alles löschen“ (Meine Daten) löscht das Gespräch für beide Seiten, egal wer "
        "es auslöst. Nachrichten werden nicht an die KI gesendet."
    ),
    "messages.made_up_only": (
        "Verwenden Sie nur erfundene Daten: Schreiben Sie keine echten Gesundheitsdaten."
    ),
    "messages.pick": "Gespräch",
    "messages.with": "Gespräch mit {name}",
    "messages.ended_suffix": "{name} (beendet)",
    "messages.ended": (
        "Diese Verbindung ist beendet: Sie beide können das Gespräch weiter lesen, aber keiner "
        "von Ihnen kann senden."
    ),
    "messages.none_coach": (
        "Noch keine Gespräche: Ein Gespräch beginnt, wenn sich ein Klient mit Ihrem Code verbindet."
    ),
    "messages.none_gymer": (
        "Noch keine Gespräche: Verbinden Sie sich unter „Coach und Freigaben“ mit einem Coach."
    ),
    "messages.realtime_off": (
        "Echtzeit-Nachrichten sind aus, daher können Sie dieses Gespräch lesen, aber nicht "
        "senden: Starten Sie die App mit `streamlit run serve.py` statt `streamlit run app.py`."
    ),
    "messages.wrong_address": (
        "Echtzeit-Nachrichten funktionieren nur, wenn die App unter {address} geöffnet ist; hier "
        "können Sie dieses Gespräch lesen, aber nicht senden."
    ),
    "messages.send": "Senden",
    "messages.placeholder": "Nachricht schreiben (Strg+Enter sendet)",
    "messages.you": "Sie",
    "messages.empty": "Noch keine Nachrichten.",
    "messages.connecting": "Verbindung wird hergestellt …",
    "messages.live": "Verbunden: Neue Nachrichten erscheinen hier.",
    "messages.stopped": "Nicht verbunden. Laden Sie die Seite neu, um es erneut zu versuchen.",
    "messages.not_sent": "Ihre Nachricht wurde nicht gesendet.",
    "messages.too_long": (
        f"Die Nachricht ist zu lang: höchstens {_MAX:,} Zeichen.".replace(",", ".")
    ),
    "messages.other_thread": "Neue Nachricht in einem anderen Gespräch.",
}
