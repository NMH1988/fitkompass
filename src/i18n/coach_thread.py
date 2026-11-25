"""The texts of consent (b), the coach's AI and the client's thread (T11.6a), and its chat line."""

from src import config

EN: dict[str, str] = {
    "coach_ai.title": "Your coach's AI and your conversation",
    # Consent (b) of docs/PRD.md: its common part and each use's part make that use's text, whose
    # version (src/coach_thread.py) changes when either changes, so the gymer is asked again for
    # that use alone. The coach's name is shown, never part of the version.
    "coach_ai.consent_intro": (
        "Consent (Art. 9 GDPR) to AI help with your conversation with your coach, {coach}. Each "
        "use below is switched on or off on its own, at any time, with one click; switching one "
        "off stops it before the next AI call and changes nothing else in your coaching. For a use "
        "you switch on, messages of your conversation, yours and {coach}'s, are sent through "
        "OpenRouter to an AI model and on to the model's provider, {provider}. Your messages can "
        "hold health data, and everything in a message goes with it, other people's names "
        "included. The app's automatic checks leave out messages they flag (for example about "
        "pain or an injury), but they can miss some. This consent is given to {coach} only and "
        "ends when your coaching ends."
    ),
    "coach_ai.use_chat": (
        "**{coach}'s AI chat reads your conversation.** When {coach} asks their AI chat about "
        "your messages (for example for a summary of a week), the messages of the week they ask "
        "about, which can be any week of your coaching with {coach}, also messages written "
        "before you switched this on, at most {count} (the newest), are sent as above, and the "
        "AI answers {coach} in their chat. The app does not store the answer, but {coach} can "
        "download their chat, with its answers, as a PDF. Switched off, the chat no longer reads "
        "your messages from its next AI call on."
    ),
    "coach_ai.on": "On",
    "coach_ai.off": "Off",
    "coach_ai.turn_on": "Switch on",
    "coach_ai.turn_off": "Switch off",
    "coach_ai.changed": (
        "The text of this use has changed since you switched it on: switch it on again to keep it."
    ),
    "coach_ai.turned_on": "Switched on.",
    "coach_ai.turned_off": "Switched off: your messages are not sent to an AI model for this use.",
    "tool.title.get_client_thread": "A client's messages",
    "answer.search_off": config.SEARCH_OFF_MESSAGE,
    "memory.refused.thread": (
        "No preference is saved in a chat that holds a client's messages: start a new chat to "
        "ask me to remember one."
    ),
    "coach_ai.col_from": "From",
    "coach_ai.col_day": "Day",
    "coach_ai.col_time": "Time",
    "coach_ai.col_text": "Message",
    "coach_ai.from_client": "Client",
    "coach_ai.from_coach": "You",
    "coach_ai.week": "Week of {start} to {end}",
    # Under a coach's chat answer, written by the page, never by the model.
    "coach_ai.left_out": (
        "{count} message(s) of this client's conversation were left out by the app's checks and "
        "not read by the AI. Read them in the conversation on the Messages page: one may be about "
        "pain or an injury."
    ),
}

DE: dict[str, str] = {
    "coach_ai.title": "Die KI Ihres Coachs und Ihr Gespräch",
    "coach_ai.consent_intro": (
        "Einwilligung (Art. 9 DSGVO) in KI-Hilfe zu Ihrem Gespräch mit Ihrem Coach, {coach}. "
        "Jede Nutzung unten wird für sich ein- oder ausgeschaltet, jederzeit, mit einem Klick; "
        "das Ausschalten einer Nutzung stoppt sie vor dem nächsten KI-Aufruf und ändert sonst "
        "nichts an Ihrem Coaching. Für eine Nutzung, die Sie einschalten, werden Nachrichten Ihres "
        "Gesprächs, Ihre und die von {coach}, über OpenRouter an ein KI-Modell und weiter an "
        "dessen Anbieter, {provider}, gesendet. Ihre Nachrichten können Gesundheitsdaten "
        "enthalten, und alles in einer Nachricht wird mitgesendet, auch Namen anderer Personen. "
        "Die automatischen Prüfungen der App lassen Nachrichten aus, die sie erkennen (zum "
        "Beispiel zu Schmerzen oder einer Verletzung), können aber einige übersehen. Diese "
        "Einwilligung gilt nur für {coach} und endet mit Ihrem Coaching."
    ),
    "coach_ai.use_chat": (
        "**Der KI-Chat von {coach} liest Ihr Gespräch.** Wenn {coach} den KI-Chat nach Ihren "
        "Nachrichten fragt (zum Beispiel nach einer Zusammenfassung einer Woche), werden die "
        "Nachrichten der gefragten Woche, die jede Woche Ihres Coachings mit {coach} sein kann, "
        "auch vor dem Einschalten geschriebene, höchstens {count} (die neuesten), wie oben "
        "gesendet, und die KI antwortet {coach} im Chat. Die App speichert die Antwort nicht, "
        "aber {coach} kann den Chat mit seinen Antworten als PDF herunterladen. Ausgeschaltet "
        "liest der Chat Ihre Nachrichten ab seinem nächsten KI-Aufruf nicht mehr."
    ),
    "coach_ai.on": "Ein",
    "coach_ai.off": "Aus",
    "coach_ai.turn_on": "Einschalten",
    "coach_ai.turn_off": "Ausschalten",
    "coach_ai.changed": (
        "Der Text dieser Nutzung hat sich geändert, seit Sie sie eingeschaltet haben: Schalten Sie "
        "sie erneut ein, um sie beizubehalten."
    ),
    "coach_ai.turned_on": "Eingeschaltet.",
    "coach_ai.turned_off": (
        "Ausgeschaltet: Ihre Nachrichten werden für diese Nutzung nicht an ein KI-Modell gesendet."
    ),
    "tool.title.get_client_thread": "Nachrichten eines Klienten",
    "answer.search_off": (
        "Die Recherche ist in einem Chat mit Nachrichten eines Klienten ausgeschaltet, daher "
        "wurde diese Frage nicht in unseren Quellen nachgeschlagen, und es wird keine "
        "Vorliebe gespeichert. Beginnen Sie einen neuen Chat für eine Recherchefrage oder um "
        "sich etwas merken zu lassen."
    ),
    "memory.refused.thread": (
        "In einem Chat mit Nachrichten eines Klienten wird keine Vorliebe gespeichert: Beginnen "
        "Sie einen neuen Chat, um mich etwas merken zu lassen."
    ),
    "coach_ai.col_from": "Von",
    "coach_ai.col_day": "Tag",
    "coach_ai.col_time": "Uhrzeit",
    "coach_ai.col_text": "Nachricht",
    "coach_ai.from_client": "Klient",
    "coach_ai.from_coach": "Sie",
    "coach_ai.week": "Woche vom {start} bis {end}",
    "coach_ai.left_out": (
        "{count} Nachricht(en) des Gesprächs mit diesem Klienten hat die App bei ihren Prüfungen "
        "ausgelassen; die KI hat sie nicht gelesen. Lesen Sie sie im Gespräch auf der Seite "
        "Nachrichten: Eine könnte von Schmerzen oder einer Verletzung handeln."
    ),
}
