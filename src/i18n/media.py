"""The texts of the drafts from a gymer's photo or voice note (T11.10): consent (c), the steps."""

from src import config

EN: dict[str, str] = {
    "media.title": "AI drafts of log entries from a photo or a voice note",
    # Consent (c) of docs/PRD.md: its version is worked out from this text in both languages
    # (src/media.py), so changing it asks every gymer again before the next draft.
    "media.consent_text": (
        "Consent (Art. 9 GDPR) to drafts of log entries from your photos and voice notes. When you "
        'press "Draft entries" under a photo (JPG or PNG, at most {mb} MB, uploaded or taken with '
        "your camera) or a voice note (recorded here, at most {seconds} seconds), the whole file "
        "is sent to an AI model through OpenRouter and on to the model's provider, {provider}, "
        "which describes the foods, drinks and amounts in the photo or writes down the words you "
        "said. The photo's metadata (location, device, time) and the recording's tags are removed "
        "first, but everything the file shows or holds goes with it, before any safety check of "
        "the app can read it: keep other people, documents and labels out of the photo, and "
        "record only your own voice. OpenRouter and {provider} handle the file under their own "
        "terms, which can let them keep it for a time (for example to check for abuse). The AI's "
        "text is then checked by the app and, if it passes, sent to an AI model again, through "
        "OpenRouter to {provider}, to draft food, weight and workout entries for you to check. "
        "Photos and voice notes can hold health data. The app keeps the file and the AI's text in "
        "memory only and never saves them. Nothing is logged until you approve a draft. You can "
        "withdraw this consent at any time with one click: that stops the next draft and drops "
        "the drafts you have not saved. Without it, no photo or voice note is sent to an AI "
        "model, and nothing else in the app changes."
    ),
    "media.consent_changed": (
        "The text of this consent has changed since you agreed to it: give it again to draft "
        "entries from a photo or a voice note."
    ),
    "media.consent_withdrawn": (
        "Consent withdrawn: no photo or voice note of yours is sent to an AI model."
    ),
    "media.source": "Draft from",
    "media.source.upload": "Upload a photo",
    "media.source.camera": "Take a photo",
    "media.source.voice": "Record a voice note",
    "media.keep_out": (
        "The whole file goes to OpenRouter and {provider} before the app can check it: keep other "
        "people, documents and labels out of the photo, and record only your own voice."
    ),
    "media.made_up": (
        "While the app holds made-up data: photograph a staged meal with no one, no document and "
        "no label in view, and play a prepared synthetic recording of made-up entries into the "
        "microphone instead of speaking yourself."
    ),
    "media.made_up_photo": (
        "While the app holds made-up data, photograph a staged meal with no one in view."
    ),
    "media.made_up_voice": (
        "While the app holds made-up data, play a prepared synthetic recording of made-up entries "
        "into the microphone instead of your own voice."
    ),
    "media.upload": "Photo of your meal (JPG or PNG, at most {mb} MB)",
    "media.camera": "Photo of your meal",
    "media.voice": "Voice note (at most {seconds} seconds)",
    "media.voice_help": (
        "Say what you ate and how much, your weight, or the sets you did. Only your own voice."
    ),
    "media.button": "Draft entries",
    "media.button_help": "Sends this file to the AI model, then shows the drafts for you to check.",
    "media.working": "Reading the file and drafting entries…",
    "media.ai_label.photo": (
        "Drafted by an AI model ({provider} through OpenRouter) from your photo; the values come "
        "from the USDA table and the app's checks. Check every card: nothing is logged until you "
        "save."
    ),
    "media.ai_label.voice": (
        "Drafted by an AI model ({provider} through OpenRouter) from your voice note; the values "
        "come from the USDA table and the app's checks. Check every card: nothing is logged until "
        "you save."
    ),
    "media.read_as.photo": "What the AI saw in your photo",
    "media.read_as.voice": "What the AI heard in your voice note",
    "media.photo_too_big": (
        "This photo is too big (at most {mb} MB and {megapixels} megapixels). Nothing was sent."
    ),
    "media.photo_type": "Only JPG and PNG photos can be used. Nothing was sent.",
    "media.photo_unreadable": "This file could not be read as a photo. Nothing was sent.",
    "media.voice_too_long": (
        "This voice note is longer than {seconds} seconds. Record a shorter one. Nothing was sent."
    ),
    "media.voice_unreadable": "This recording could not be read. Nothing was sent.",
    "media.voice_empty": "This recording is empty. Nothing was sent.",
    "media.nothing": "The AI found no food, weight or workout to draft in this file.",
    "media.refused": (
        "The safety check left out what the AI read in this file: nothing was drafted and nothing "
        "more was sent to the AI."
    ),
    "media.no_consent": "Give the consent above to draft entries from a photo or a voice note.",
    "media.error": "Nothing was logged. You can try again.",
    "media.done": "Done. Entries logged: {count}.",
    "media.dropped": "Entries dropped because they could not be checked: {count}.",
    "prompt.media_missing": config.MEDIA_PROMPT_MISSING_MESSAGE,
}

DE: dict[str, str] = {
    "media.title": "KI-Entwürfe von Tagebucheinträgen aus einem Foto oder einer Sprachnachricht",
    "media.consent_text": (
        "Einwilligung (Art. 9 DSGVO) in Entwürfe von Tagebucheinträgen aus Ihren Fotos und "
        "Sprachnachrichten. Wenn Sie unter einem Foto (JPG oder PNG, höchstens {mb} MB, "
        "hochgeladen oder mit Ihrer Kamera aufgenommen) oder einer Sprachnachricht (hier "
        'aufgenommen, höchstens {seconds} Sekunden) auf „Einträge entwerfen" drücken, wird die '
        "ganze Datei über OpenRouter an ein KI-Modell und weiter an dessen Anbieter, {provider}, "
        "gesendet, das die Lebensmittel, Getränke und Mengen auf dem Foto beschreibt oder die "
        "gesprochenen Worte aufschreibt. Die Metadaten des Fotos (Ort, Gerät, Zeit) und die Tags "
        "der Aufnahme werden vorher entfernt, aber alles, was die Datei zeigt oder enthält, geht "
        "mit, bevor eine Sicherheitsprüfung der App es lesen kann: Halten Sie andere Personen, "
        "Dokumente und Etiketten aus dem Foto heraus und nehmen Sie nur Ihre eigene Stimme auf. "
        "OpenRouter und {provider} verarbeiten die Datei nach ihren eigenen Bedingungen, die "
        "ihnen erlauben können, sie eine Zeit lang aufzubewahren (zum Beispiel zur Prüfung auf "
        "Missbrauch). Der Text der KI wird dann von der App geprüft und, wenn er die Prüfung "
        "besteht, erneut über OpenRouter an ein KI-Modell von {provider} gesendet, das Einträge "
        "zu Essen, Gewicht und Training entwirft, die Sie prüfen. Fotos und Sprachnachrichten "
        "können Gesundheitsdaten enthalten. Die App behält die Datei und den Text der KI nur im "
        "Arbeitsspeicher und speichert sie nie. Nichts wird eingetragen, bevor Sie einen Entwurf "
        "freigeben. Sie können diese Einwilligung jederzeit mit einem Klick widerrufen: Das "
        "stoppt den nächsten Entwurf und verwirft die Entwürfe, die Sie noch nicht gespeichert "
        "haben. Ohne sie wird kein Foto und keine Sprachnachricht an ein KI-Modell gesendet, und "
        "sonst ändert sich nichts in der App."
    ),
    "media.consent_changed": (
        "Der Text dieser Einwilligung hat sich geändert, seit Sie zugestimmt haben: Geben Sie sie "
        "erneut, um Einträge aus einem Foto oder einer Sprachnachricht zu entwerfen."
    ),
    "media.consent_withdrawn": (
        "Einwilligung widerrufen: Kein Foto und keine Sprachnachricht von Ihnen wird an ein "
        "KI-Modell gesendet."
    ),
    "media.source": "Entwurf aus",
    "media.source.upload": "Foto hochladen",
    "media.source.camera": "Foto aufnehmen",
    "media.source.voice": "Sprachnachricht aufnehmen",
    "media.keep_out": (
        "Die ganze Datei geht an OpenRouter und {provider}, bevor die App sie prüfen kann: Halten "
        "Sie andere Personen, Dokumente und Etiketten aus dem Foto heraus und nehmen Sie nur Ihre "
        "eigene Stimme auf."
    ),
    "media.made_up": (
        "Solange die App erfundene Daten enthält: Fotografieren Sie eine gestellte Mahlzeit ohne "
        "Personen, Dokumente und Etiketten im Bild, und spielen Sie statt Ihrer eigenen Stimme "
        "eine vorbereitete synthetische Aufnahme erfundener Einträge in das Mikrofon ab."
    ),
    "media.made_up_photo": (
        "Solange die App erfundene Daten enthält, fotografieren Sie eine gestellte Mahlzeit ohne "
        "Personen im Bild."
    ),
    "media.made_up_voice": (
        "Solange die App erfundene Daten enthält, spielen Sie statt Ihrer eigenen Stimme eine "
        "vorbereitete synthetische Aufnahme erfundener Einträge in das Mikrofon ab."
    ),
    "media.upload": "Foto Ihrer Mahlzeit (JPG oder PNG, höchstens {mb} MB)",
    "media.camera": "Foto Ihrer Mahlzeit",
    "media.voice": "Sprachnachricht (höchstens {seconds} Sekunden)",
    "media.voice_help": (
        "Sagen Sie, was und wie viel Sie gegessen haben, Ihr Gewicht oder Ihre Sätze. Nur Ihre "
        "eigene Stimme."
    ),
    "media.button": "Einträge entwerfen",
    "media.button_help": (
        "Sendet diese Datei an das KI-Modell und zeigt dann die Entwürfe zur Prüfung."
    ),
    "media.working": "Die Datei wird gelesen und Einträge werden entworfen …",
    "media.ai_label.photo": (
        "Von einem KI-Modell ({provider} über OpenRouter) aus Ihrem Foto entworfen; die Werte "
        "stammen aus der USDA-Tabelle und den Prüfungen der App. Prüfen Sie jede Karte: Nichts "
        "wird eingetragen, bevor Sie speichern."
    ),
    "media.ai_label.voice": (
        "Von einem KI-Modell ({provider} über OpenRouter) aus Ihrer Sprachnachricht entworfen; "
        "die Werte stammen aus der USDA-Tabelle und den Prüfungen der App. Prüfen Sie jede Karte: "
        "Nichts wird eingetragen, bevor Sie speichern."
    ),
    "media.read_as.photo": "Was die KI auf Ihrem Foto gesehen hat",
    "media.read_as.voice": "Was die KI in Ihrer Sprachnachricht gehört hat",
    "media.photo_too_big": (
        "Dieses Foto ist zu groß (höchstens {mb} MB und {megapixels} Megapixel). Es wurde nichts "
        "gesendet."
    ),
    "media.photo_type": "Nur JPG- und PNG-Fotos sind möglich. Es wurde nichts gesendet.",
    "media.photo_unreadable": (
        "Diese Datei konnte nicht als Foto gelesen werden. Es wurde nichts gesendet."
    ),
    "media.voice_too_long": (
        "Diese Sprachnachricht ist länger als {seconds} Sekunden. Nehmen Sie eine kürzere auf. "
        "Es wurde nichts gesendet."
    ),
    "media.voice_unreadable": (
        "Diese Aufnahme konnte nicht gelesen werden. Es wurde nichts gesendet."
    ),
    "media.voice_empty": "Diese Aufnahme ist leer. Es wurde nichts gesendet.",
    "media.nothing": (
        "Die KI hat in dieser Datei kein Essen, kein Gewicht und kein Training zum Entwerfen "
        "gefunden."
    ),
    "media.refused": (
        "Die Sicherheitsprüfung hat aussortiert, was die KI in dieser Datei gelesen hat: Es wurde "
        "nichts entworfen und nichts weiter an die KI gesendet."
    ),
    "media.no_consent": (
        "Geben Sie oben die Einwilligung, um Einträge aus einem Foto oder einer Sprachnachricht "
        "zu entwerfen."
    ),
    "media.error": "Es wurde nichts eingetragen. Sie können es erneut versuchen.",
    "media.done": "Fertig. Eingetragene Einträge: {count}.",
    "media.dropped": "Verworfene Einträge, weil sie nicht geprüft werden konnten: {count}.",
    "prompt.media_missing": (
        "Die Anweisung zum Lesen eines Fotos oder einer Sprachnachricht "
        "(`src/prompts/media_photo_system.md` oder `src/prompts/media_voice_system.md`) fehlt oder "
        "ist leer, daher kann daraus nichts entworfen werden. Stellen Sie die Datei wieder her und "
        "versuchen Sie es erneut."
    ),
}
