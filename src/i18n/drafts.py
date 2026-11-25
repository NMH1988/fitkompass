"""The texts of the drafts from a gymer's own messages (T11.5): consent (a) and the draft cards."""

from src import config

EN: dict[str, str] = {
    "drafts.title": "AI drafts of log entries from your messages",
    # Consent (a) of docs/PRD.md: its version is worked out from this text in both languages
    # (src/drafting.py), so changing it asks every gymer again before the next draft.
    "drafts.consent_text": (
        "Consent (Art. 9 GDPR) to drafts of log entries from your messages. When you press "
        '"Draft entries from my messages", the text of your own messages of the last '
        "{days} days in your conversation with your current coach that were not drafted yet, "
        "including those you sent before giving this consent (never your coach's messages), "
        "is sent, one message "
        "at a time, to an AI model through OpenRouter and on to the model's provider, {provider}, "
        "which drafts food, weight and workout entries for you to check. Everything in a message "
        "goes with it, other people's names included, so write only about your own food, weight "
        "and workouts. Your messages can hold health data. Nothing is logged until you approve a "
        "draft. You can withdraw this consent at any time with one "
        "click: that stops the next draft and drops the drafts you have not saved. Without it, "
        "none of your messages is sent to an AI model, and nothing else in the app changes."
    ),
    "drafts.consent_give": "Give this consent",
    "drafts.consent_withdraw": "Withdraw this consent",
    "drafts.consent_given": "You gave this consent.",
    "drafts.consent_standing": (
        "You gave your consent to AI drafts of log entries from your messages. Drafts are made "
        "only in your conversation with your current coach; you can withdraw the consent here."
    ),
    "drafts.consent_changed": (
        "The text of this consent has changed since you agreed to it: give it again to draft "
        "entries."
    ),
    "drafts.consent_withdrawn": "Consent withdrawn: none of your messages is sent to an AI model.",
    "drafts.button": "Draft entries from my messages",
    "drafts.button_help": (
        "Reads up to {count} of your messages of the last {days} days that were not drafted yet, "
        "oldest first."
    ),
    "drafts.ai_label": (
        "Drafted by an AI model ({provider} through OpenRouter) from your message; the values "
        "come from the USDA table and the app's checks. Check every card: nothing is logged until "
        "you save."
    ),
    "drafts.your_message": "Your message of {day}",
    "drafts.card_food": "Food",
    "drafts.card_weight": "Weight",
    "drafts.card_workout": "Workout",
    "drafts.action": "Decision",
    "drafts.action.approve": "Approve",
    "drafts.change": "Change the values",
    "drafts.action.reject": "Reject",
    "drafts.save": "Save decisions",
    "drafts.food": "Food (USDA)",
    "drafts.no_match": (
        "No close match in the USDA table: pick a food under Change the values, or reject the card."
    ),
    "drafts.grams": "Grams",
    "drafts.no_grams": (
        "No amount in the message: enter the grams under Change the values, or reject the card."
    ),
    "drafts.meal": "Meal",
    "drafts.day": "Day",
    "drafts.day_line": "Day: {day}",
    "drafts.grams_line": "{grams} g",
    "drafts.grams_missing": "Grams: not named",
    "drafts.read_as": "Read by the AI as: {food}",
    "drafts.already_logged": (
        "Already logged on {day}: {food}, {grams} g ({meal}). Reject this card if it is the same "
        "food eaten once."
    ),
    "drafts.meal_placeholder": "Not named: pick one",
    "drafts.progress": "Message {position} of {total} in this run",
    "drafts.skipped": (
        "{count} passed over (no entry found, left out by the safety check, or handled elsewhere)"
    ),
    "drafts.weight_kg": "Weight (kg)",
    "drafts.reps": "Reps",
    "drafts.load_kg": "kg",
    "drafts.set": "Set {number}",
    "drafts.nutrients": (
        "{kcal} kcal · {protein} g protein · {carbs} g carbohydrate · {fat} g fat"
    ),
    "drafts.saved": "Saved. Entries logged: {count}.",
    "drafts.already": (
        "This message was already handled (in another tab, say): nothing was logged again."
    ),
    "drafts.nothing": "No new messages of yours to draft.",
    "drafts.done": (
        "Done. Cards drafted: {cards}. Messages left out by the safety check and not sent to the "
        "AI: {refused}. Entries dropped because they could not be checked: {dropped}."
    ),
    "drafts.no_consent": "Give the consent above to draft entries from your messages.",
    "drafts.error": (
        "Nothing more was logged; the messages left are drafted again on your next press."
    ),
    "drafts.workout_invalid": (
        "A set is outside the workout log's ranges or names no exercise of the list."
    ),
    "drafts.decision_invalid": "Decide every card of this message before you save.",
    "drafts.entry_invalid": "A value is outside the ranges the app can log.",
    "drafts.only_active": "Drafts are made only from a conversation with your current coach.",
    "drafts.rate_window": (
        "You are asking for drafts too fast. Please wait {seconds} s and try again."
    ),
    "drafts.rate_session": (
        "This session has reached its limit of {limit} requests to the AI model (questions, "
        "reviews and drafts)."
    ),
    "prompt.drafts_missing": config.DRAFT_PROMPT_MISSING_MESSAGE,
}

DE: dict[str, str] = {
    "drafts.title": "KI-Entwürfe von Tagebucheinträgen aus Ihren Nachrichten",
    "drafts.consent_text": (
        "Einwilligung (Art. 9 DSGVO) in Entwürfe von Tagebucheinträgen aus Ihren Nachrichten. "
        "Wenn Sie auf „Einträge aus meinen Nachrichten entwerfen“ klicken, wird der Text Ihrer "
        "eigenen, noch nicht entworfenen Nachrichten der letzten {days} Tage im Gespräch mit Ihrem "
        "aktuellen Coach, auch der vor dieser Einwilligung gesendeten (nie die Nachrichten Ihres "
        "Coachs), einzeln über OpenRouter an ein KI-Modell und weiter an dessen Anbieter, "
        "{provider}, gesendet, der Einträge zu Essen, Gewicht und Training entwirft, die Sie "
        "prüfen. Alles in einer Nachricht wird mitgesendet, auch Namen anderer Personen; schreiben "
        "Sie daher nur über Ihr eigenes Essen, Ihr Gewicht und Ihr Training. Ihre Nachrichten "
        "können Gesundheitsdaten enthalten. Nichts wird eingetragen, bevor Sie einen Entwurf "
        "bestätigen. Sie können diese Einwilligung jederzeit mit einem Klick widerrufen: Das "
        "stoppt den nächsten Entwurf und verwirft die Entwürfe, die Sie noch nicht gespeichert "
        "haben. Ohne sie wird keine Ihrer Nachrichten an ein KI-Modell gesendet, und sonst ändert "
        "sich nichts in der App."
    ),
    "drafts.consent_give": "Einwilligung erteilen",
    "drafts.consent_withdraw": "Einwilligung widerrufen",
    "drafts.consent_given": "Sie haben diese Einwilligung erteilt.",
    "drafts.consent_standing": (
        "Sie haben in KI-Entwürfe von Tagebucheinträgen aus Ihren Nachrichten eingewilligt. "
        "Entwürfe entstehen nur im Gespräch mit Ihrem aktuellen Coach; Sie können die "
        "Einwilligung hier widerrufen."
    ),
    "drafts.consent_changed": (
        "Der Text dieser Einwilligung hat sich geändert, seit Sie zugestimmt haben: Erteilen Sie "
        "sie erneut, um Einträge zu entwerfen."
    ),
    "drafts.consent_withdrawn": (
        "Einwilligung widerrufen: Keine Ihrer Nachrichten wird an ein KI-Modell gesendet."
    ),
    "drafts.button": "Einträge aus meinen Nachrichten entwerfen",
    "drafts.button_help": (
        "Liest bis zu {count} Ihrer noch nicht entworfenen Nachrichten der letzten {days} Tage, "
        "die älteste zuerst."
    ),
    "drafts.ai_label": (
        "Von einem KI-Modell ({provider} über OpenRouter) aus Ihrer Nachricht entworfen; die Werte "
        "stammen aus der USDA-Tabelle und den Prüfungen der App. Prüfen Sie jede Karte: Nichts "
        "wird eingetragen, bevor Sie speichern."
    ),
    "drafts.your_message": "Ihre Nachricht vom {day}",
    "drafts.card_food": "Essen",
    "drafts.card_weight": "Gewicht",
    "drafts.card_workout": "Training",
    "drafts.action": "Entscheidung",
    "drafts.action.approve": "Bestätigen",
    "drafts.change": "Werte ändern",
    "drafts.action.reject": "Ablehnen",
    "drafts.save": "Entscheidungen speichern",
    "drafts.food": "Lebensmittel (USDA)",
    "drafts.no_match": (
        "Keine passende Entsprechung in der USDA-Tabelle: Wählen Sie unter „Werte ändern“ ein "
        "Lebensmittel, oder lehnen Sie die Karte ab."
    ),
    "drafts.grams": "Gramm",
    "drafts.no_grams": (
        "Keine Menge in der Nachricht: Geben Sie unter „Werte ändern“ die Gramm ein, oder "
        "lehnen Sie die Karte ab."
    ),
    "drafts.meal": "Mahlzeit",
    "drafts.day": "Tag",
    "drafts.day_line": "Tag: {day}",
    "drafts.grams_line": "{grams} g",
    "drafts.grams_missing": "Gramm: nicht genannt",
    "drafts.read_as": "Von der KI gelesen als: {food}",
    "drafts.already_logged": (
        "Bereits am {day} eingetragen: {food}, {grams} g ({meal}). Lehnen Sie diese Karte ab, "
        "wenn es dasselbe, nur einmal gegessene Lebensmittel ist."
    ),
    "drafts.meal_placeholder": "Nicht genannt: bitte wählen",
    "drafts.progress": "Nachricht {position} von {total} in diesem Durchgang",
    "drafts.skipped": (
        "{count} übersprungen (kein Eintrag gefunden, von der Sicherheitsprüfung ausgelassen "
        "oder anderswo erledigt)"
    ),
    "drafts.weight_kg": "Gewicht (kg)",
    "drafts.reps": "Wiederholungen",
    "drafts.load_kg": "kg",
    "drafts.set": "Satz {number}",
    "drafts.nutrients": (
        "{kcal} kcal · {protein} g Eiweiß · {carbs} g Kohlenhydrate · {fat} g Fett"
    ),
    "drafts.saved": "Gespeichert. Eingetragene Einträge: {count}.",
    "drafts.already": (
        "Diese Nachricht wurde schon bearbeitet (etwa in einem anderen Tab): Nichts wurde erneut "
        "eingetragen."
    ),
    "drafts.nothing": "Keine neuen Nachrichten von Ihnen zum Entwerfen.",
    "drafts.done": (
        "Fertig. Entworfene Karten: {cards}. Von der Sicherheitsprüfung ausgelassene und nicht an "
        "die KI gesendete Nachrichten: {refused}. Verworfene Einträge, weil sie nicht geprüft "
        "werden konnten: {dropped}."
    ),
    "drafts.no_consent": (
        "Erteilen Sie oben die Einwilligung, um Einträge aus Ihren Nachrichten zu entwerfen."
    ),
    "drafts.error": (
        "Es wurde nichts weiter eingetragen; die übrigen Nachrichten werden beim nächsten Klick "
        "erneut entworfen."
    ),
    "drafts.workout_invalid": (
        "Ein Satz liegt außerhalb der Bereiche des Trainingstagebuchs oder nennt keine Übung der "
        "Liste."
    ),
    "drafts.decision_invalid": "Entscheiden Sie jede Karte dieser Nachricht, bevor Sie speichern.",
    "drafts.entry_invalid": "Ein Wert liegt außerhalb der Bereiche, die die App eintragen kann.",
    "drafts.only_active": "Entwürfe entstehen nur aus einem Gespräch mit Ihrem aktuellen Coach.",
    "drafts.rate_window": (
        "Sie fordern Entwürfe zu schnell an. Bitte warten Sie {seconds} s und versuchen Sie es "
        "erneut."
    ),
    "drafts.rate_session": (
        "Diese Sitzung hat ihr Limit von {limit} Anfragen an das KI-Modell erreicht (Fragen, "
        "Berichte und Entwürfe)."
    ),
    "prompt.drafts_missing": (
        "Die Anweisung für Entwürfe von Tagebucheinträgen (`src/prompts/draft_entries_system.md`) "
        "fehlt oder ist leer, daher kann kein Eintrag entworfen werden. Stellen Sie die Datei "
        "wieder her und versuchen Sie es erneut."
    ),
}
