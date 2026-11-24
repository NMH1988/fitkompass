"""The food texts: lookup, the plan check, Today, suggested foods and the coach's meal plan."""

from src import config
from src.i18n.core import plain

# The calorie floor as each language writes a thousand (the coach's meal plan, T11.7).
_FLOOR_EN = f"{config.CALORIE_FLOOR_KCAL:,}"
_FLOOR_DE = _FLOOR_EN.replace(",", ".")

EN: dict[str, str] = {
    # Food lookup (tab and tool result) and the meal plan check.
    "food.title": "Food lookup",
    "food.food": "Food",
    "food.placeholder": "Choose a food or type to search",
    "food.grams": "Grams",
    "food.look_up": "Look up",
    "food.caption": (
        "Pick a food from the list, or type a few letters to search it. Single, unprocessed foods "
        "from the USDA FoodData Central Foundation Foods table, named in English."
    ),
    # The Food lookup tab's own messages, in the UI's language as no model reads them (T7.1). The
    # English tab shows the lookup's own fixed text (`lookup_chosen_food()`, T4.8).
    "food.tab.invalid": (
        "Invalid food lookup: choose one food from the list; the amount must be a number of "
        "grams from 0.1 to 2000."
    ),
    "food.tab.error": config.TOOL_FAILED_MESSAGE,
    "food.did_you_mean": "Did you mean",
    "food.matched": "Matched USDA food, {grams} g:",
    "food.fiber_line": "Fiber: {fiber}",
    "food.not_reported": "not reported",
    "food.close_alternatives": "Close alternatives",
    "food.usda_food": "USDA food",
    "food.amount": "Amount",
    "usda.source_line": config.USDA_SOURCE_LINE,
    # A food found through the FoodData Central API (T9.9); {data_type} is USDA's own name of the
    # data type ("SR Legacy"), kept in English like the food names.
    "usda.api_source_line": config.FOOD_API_SOURCE_LINE,
    "meal.source_line": config.MEAL_PLAN_SOURCE_LINE,
    "meal.food_asked": "Food asked",
    "meal.other_names": "Other close USDA names",
    "meal.not_found": "Not found",
    "meal.nutrient": "Nutrient",
    "meal.plan_total": "Plan total",
    "meal.daily_target": "Daily target",
    "meal.difference": "Difference",
    "meal.range": "Range from the sources",
    "meal.below_target": "{amount} below the target",
    "meal.above_target": "{amount} above the target",
    "meal.on_target": "On the target",
    "meal.range.below": "Below {span} {unit}",
    "meal.range.within": "Within {span} {unit}",
    "meal.range.above": "Above {span} {unit}",
    "meal.no_target": "No target",
    # The foods a coach suggests to a client (T9.34): a list to choose from, never a meal plan.
    "suggestions.heading": "Suggested by your coach",
    "suggestions.gymer_intro": (
        "Foods your coach suggests, to choose from. This is not a meal plan, and the foods "
        "together are not a day's intake: you may eat other foods too. Log one with its "
        "button; you can change the grams first, and the meal afterwards in the day's list."
    ),
    "suggestions.item": (
        "{food}, {grams} g · {kcal} kcal, {protein} g protein, {carbs} g carbohydrate, {fat} g fat"
    ),
    "suggestions.item_no_kcal": "{food}, {grams} g",
    "suggestions.grams": "Grams",
    "suggestions.log": "Log",
    "suggestions.logged": "Food added from your coach's suggestions.",
    "suggestions.gone": (
        "This food is no longer on your coach's list, so nothing was saved. The list is up to date."
    ),
    "suggestions.coach_heading": "Suggested foods",
    "suggestions.coach_intro": (
        "Suggest foods for this client to choose from. Each save replaces the list; an empty list "
        "clears it. It is not a meal plan: the client may eat other foods, so the calorie floor "
        "does not apply to the list's total, shown next to the client's target for information."
    ),
    "suggestions.not_shared": "Foods can be suggested only while the client shares nutrition.",
    "suggestions.draft_empty": "No foods in the list.",
    "suggestions.add_row": "Add to the list",
    "suggestions.remove_pick": "Food to remove",
    "suggestions.remove": "Remove from the list",
    "suggestions.save": "Save the list",
    "suggestions.saved": "The suggested foods were saved; the client sees them on Today.",
    "suggestions.refused": ("The list was not saved: you cannot suggest foods to this client now."),
    "suggestions.invalid": (
        f"The list was not saved: give every food a meal and an amount within range, at most "
        f"{config.MAX_SUGGESTED_FOODS} foods."
    ),
    "suggestions.twice": "A food is in one meal twice; remove one of them.",
    "suggestions.full": f"The list holds at most {config.MAX_SUGGESTED_FOODS} foods.",
    "suggestions.total": (
        "List total: {kcal} kcal, {protein} g protein, {carbs} g carbohydrate, {fat} g fat."
    ),
    "suggestions.target": (
        "The client's targets today: {kcal} kcal, {protein} g protein, {carbs} g carbohydrate, "
        "{fat} g fat."
    ),
    "suggestions.no_target": "The client has no daily targets today.",
    "suggestions.share": (
        "In the week shown, the client logged {suggested} of {items} foods from a coach's "
        "suggestions ({share} of the energy)."
    ),
    "suggestions.share_no_energy": (
        "In the week shown, the client logged {suggested} of {items} foods from a coach's "
        "suggestions."
    ),
    "suggestions.share_none": "The client logged no food in the week shown.",
    # The coach's meal plan for a client (T11.7): one template day, read-only for the gymer.
    "meal_plan.coach_heading": "Meal plan",
    "meal_plan.coach_intro": (
        "One day of meals for this client, the same for every day. Each save replaces the plan "
        "and tells the client, who reads it on their Meal plan page but logs what they really "
        f"eat. A plan's day total is never below {_FLOOR_EN} kcal, the app's calorie floor. The "
        "app does not check allergens or intolerances: ask your client about them."
    ),
    "meal_plan.not_shared": "A meal plan can be set only while the client shares nutrition.",
    "meal_plan.draft_empty": "No foods in the plan.",
    "meal_plan.add_row": "Add to the plan",
    "meal_plan.remove_pick": "Food to remove from the plan",
    "meal_plan.remove_row": "Remove from the plan",
    "meal_plan.save": "Save the plan",
    "meal_plan.saved": "The meal plan was saved; the client sees it on their Meal plan page.",
    "meal_plan.remove_plan": "Remove the plan",
    "meal_plan.removed": "The meal plan was removed; the client no longer sees one.",
    "meal_plan.refused": "The plan was not saved: you cannot set a meal plan for this client now.",
    "meal_plan.invalid": (
        f"The plan was not saved: give every food a meal and an amount within range, at most "
        f"{config.MAX_MEAL_PLAN_FOODS} foods."
    ),
    "meal_plan.twice": "A food is in one meal twice; remove one of them.",
    "meal_plan.full": f"The plan holds at most {config.MAX_MEAL_PLAN_FOODS} foods.",
    "meal_plan.empty": "Add foods before saving, or remove the plan with its own button.",
    "meal_plan.below_floor": (
        f"The plan was not saved: its day total is below {_FLOOR_EN} kcal, the app's calorie "
        "floor. Add foods or grams first."
    ),
    "meal_plan.below_floor_draft": (
        f"The day total is below {_FLOOR_EN} kcal, the app's calorie floor, so the plan cannot be "
        "saved like this."
    ),
    "meal_plan.meal_total": (
        "{meal} total: {kcal} kcal, {protein} g protein, {carbs} g carbohydrate, {fat} g fat."
    ),
    "meal_plan.total": (
        "Day total: {kcal} kcal, {protein} g protein, {carbs} g carbohydrate, {fat} g fat."
    ),
    # The gymer's Meal plan page.
    "meal_plan.gymer_intro": (
        "The meal plan {coach} set for you: one day of meals, the same for every day. It is your "
        "coach's advice, to read here; log what you really eat on Today."
    ),
    "meal_plan.not_checked": (
        "This is your coach's plan, not the app's. The app does not check it for allergens or "
        "intolerances, and does not check a coach's qualifications: tell your coach about any "
        "allergy, and see a doctor for a medical diet."
    ),
    "meal_plan.saved_at": "Saved {when}.",
    "meal_plan.profile_first": (
        "Save your details on My profile first: the app is for adults, and your age is checked "
        "there. Then your coach's meal plan shows here."
    ),
    "meal_plan.none": "Your coach has not set a meal plan for you.",
    "meal_plan.no_coach": (
        "You have no meal plan. A meal plan comes from the coach you are connected with."
    ),
    "meal_plan.usda_note": (
        "Energy and nutrients are worked out from the USDA table when the coach saved the plan."
    ),
    # The Today page: the food and weight diary (T9.13).
    "today.intro": (
        "Log what you ate and your weight. A day with nothing logged shows as not logged, never "
        "as a day without food."
    ),
    "today.made_up_only": "Use made-up data only: do not enter real health data.",
    "today.profile_first": (
        "Save your details on My profile first (with the box ticked that you understand they are "
        "stored). Then you can log food and weight here."
    ),
    "today.day": "Day",
    "today.day_help": f"Today or up to {config.DIARY_MAX_DAYS_BACK} days back.",
    "today.add_food": "Add a food",
    "today.food": "Food",
    "today.food_placeholder": "Choose a food",
    "today.grams": "Amount (g)",
    "today.meal": "Meal",
    "today.add": "Add",
    "today.food_caption": (
        "Foods from the USDA table, in English. Each entry keeps the nutrients for the amount you "
        "logged."
    ),
    "today.day_title": "Logged on {day}",
    "today.nothing_logged": "Nothing logged on this day.",
    "today.meal_total": "**{meal}** · {kcal} kcal",
    "today.day_total": (
        "**Day total:** {kcal} kcal · protein {protein} g · carbohydrate {carbohydrate} g · "
        "fat {fat} g · fiber {fiber}"
    ),
    "today.fiber_partial": "{value} g or more (not reported for some foods)",
    "today.col.food": "Food",
    "today.col.grams": "Amount (g)",
    "today.col.kcal": "kcal",
    "today.col.protein": "Protein (g)",
    "today.col.carbohydrate": "Carbohydrate (g)",
    "today.col.fat": "Fat (g)",
    "today.col.fiber": "Fiber (g)",
    "today.edit_title": "Change or delete an entry",
    "today.entry": "Entry",
    "today.entry_placeholder": "Choose an entry",
    "today.save_changes": "Save changes",
    "today.delete": "Delete entry",
    "today.weight_title": "Weight",
    "today.weight_unit": "Weight ({unit})",
    "today.save_weight": "Save weight",
    "today.weights_logged": "Logged on this day: {weights}",
    "today.added": "Food added.",
    "today.changed": "Entry changed.",
    "today.deleted": "Entry deleted.",
    "today.weight_saved": "Weight saved.",
    "today.gone": "This entry no longer exists. The list below is up to date.",
    "today.stored_note": (
        "Saved in this app's database. You can export or delete it on My data; a coach sees "
        "it only while you share nutrition (food) or body (weight) with them."
    ),
    "diary.grams_range": (
        f"Enter an amount from {plain(config.FOOD_MIN_GRAMS, 'en')} to {config.FOOD_MAX_GRAMS} g."
    ),
    "diary.meal_needed": "Choose a meal: breakfast, lunch, dinner or snack.",
    "diary.profile_first": "Save your details on My profile first; nothing was saved here.",
    "diary.food_needed": "Choose a food from the list.",
    "diary.food_table": "The food table could not be read, so nothing was saved.",
    "diary.day_range": f"Choose today or a day up to {config.DIARY_MAX_DAYS_BACK} days back.",
    "diary.weight_range": (
        f"Enter a weight from {plain(config.PROFILE_WEIGHT_KG_RANGE[0], 'en')} to "
        f"{plain(config.PROFILE_WEIGHT_KG_RANGE[1], 'en')} kg (or the same in lb)."
    ),
}

DE: dict[str, str] = {
    "food.title": "Lebensmittelsuche",
    "food.food": "Lebensmittel",
    "food.placeholder": "Wählen Sie ein Lebensmittel oder tippen Sie zum Suchen",
    "food.grams": "Gramm",
    "food.look_up": "Suchen",
    "food.caption": (
        "Wählen Sie ein Lebensmittel aus der Liste oder geben Sie einige Buchstaben ein, um danach "
        "zu suchen. Verfügbar sind einzelne, unverarbeitete Lebensmittel aus der "
        "Foundation-Foods-Tabelle von USDA FoodData Central; die Bezeichnungen sind auf Englisch."
    ),
    "food.tab.invalid": (
        "Wählen Sie ein Lebensmittel aus der Liste und geben Sie eine Menge von 0,1 bis 2000 "
        "Gramm an."
    ),
    "food.tab.error": (
        "Die Lebensmittelsuche ist gerade nicht verfügbar: Die Lebensmitteltabelle konnte nicht "
        "gelesen werden."
    ),
    "food.did_you_mean": "Meinten Sie",
    "food.matched": "Gefundenes USDA-Lebensmittel, {grams} g:",
    "food.fiber_line": "Ballaststoffe: {fiber}",
    "food.not_reported": "nicht angegeben",
    "food.close_alternatives": "Ähnliche Einträge",
    "food.usda_food": "USDA-Lebensmittel",
    "food.amount": "Menge",
    "usda.source_line": (
        "Quelle: USDA FoodData Central, Foundation Foods (CC0). Werte pro 100 g, umgerechnet."
    ),
    "usda.api_source_line": (
        "Quelle: USDA FoodData Central API, {data_type} (CC0). Werte pro 100 g, umgerechnet."
    ),
    "meal.source_line": (
        "Quelle: USDA FoodData Central, Foundation Foods (CC0). Werte pro 100 g, umgerechnet. "
        "Ziele: die Tagesziele aus Ihren Angaben."
    ),
    "meal.food_asked": "Angefragtes Lebensmittel",
    "meal.other_names": "Weitere ähnliche USDA-Namen",
    "meal.not_found": "Nicht gefunden",
    "meal.nutrient": "Nährstoff",
    "meal.plan_total": "Summe im Plan",
    "meal.daily_target": "Tagesziel",
    "meal.difference": "Differenz",
    "meal.range": "Bereich aus den Quellen",
    "meal.below_target": "{amount} unter dem Ziel",
    "meal.above_target": "{amount} über dem Ziel",
    "meal.on_target": "Ziel erreicht",
    "meal.range.below": "Unter {span} {unit}",
    "meal.range.within": "Im Bereich {span} {unit}",
    "meal.range.above": "Über {span} {unit}",
    "meal.no_target": "Kein Ziel",
    # Vom Coach vorgeschlagene Lebensmittel (T9.34): eine Auswahl, nie ein Ernährungsplan.
    "suggestions.heading": "Von Ihrem Coach vorgeschlagen",
    "suggestions.gymer_intro": (
        "Lebensmittel, die Ihr Coach Ihnen zur Auswahl vorschlägt. Das ist kein Ernährungsplan, "
        "und zusammen ergeben sie keine Tagesmenge: Sie können auch andere Lebensmittel essen. "
        "Erfassen Sie eines mit seiner Schaltfläche; die Gramm können Sie vorher ändern, die "
        "Mahlzeit danach in der Liste des Tages."
    ),
    "suggestions.item": (
        "{food}, {grams} g · {kcal} kcal, {protein} g Protein, {carbs} g Kohlenhydrate, "
        "{fat} g Fett"
    ),
    "suggestions.item_no_kcal": "{food}, {grams} g",
    "suggestions.grams": "Gramm",
    "suggestions.log": "Erfassen",
    "suggestions.logged": "Lebensmittel aus den Vorschlägen Ihres Coachs hinzugefügt.",
    "suggestions.gone": (
        "Dieses Lebensmittel steht nicht mehr auf der Liste Ihres Coachs, daher wurde nichts "
        "gespeichert. Die Liste ist aktuell."
    ),
    "suggestions.coach_heading": "Vorgeschlagene Lebensmittel",
    "suggestions.coach_intro": (
        "Schlagen Sie diesem Klienten Lebensmittel zur Auswahl vor. Jedes Speichern ersetzt die "
        "Liste; eine leere Liste löscht die Vorschläge. Es ist kein Ernährungsplan: Der Klient "
        "kann auch andere Lebensmittel essen, daher gilt die Kaloriengrenze nicht für die Summe "
        "der Liste, die nur zur Information neben den Zielen des Klienten steht."
    ),
    "suggestions.not_shared": (
        "Lebensmittel können nur vorgeschlagen werden, solange der Klient die Ernährung teilt."
    ),
    "suggestions.draft_empty": "Keine Lebensmittel in der Liste.",
    "suggestions.add_row": "Zur Liste hinzufügen",
    "suggestions.remove_pick": "Zu entfernendes Lebensmittel",
    "suggestions.remove": "Aus der Liste entfernen",
    "suggestions.save": "Liste speichern",
    "suggestions.saved": (
        "Die vorgeschlagenen Lebensmittel wurden gespeichert; der Klient sieht sie unter Heute."
    ),
    "suggestions.refused": (
        "Die Liste wurde nicht gespeichert: Sie können diesem Klienten jetzt keine Lebensmittel "
        "vorschlagen."
    ),
    "suggestions.invalid": (
        f"Die Liste wurde nicht gespeichert: Geben Sie jedem Lebensmittel eine Mahlzeit und eine "
        f"Menge im erlaubten Bereich, höchstens {config.MAX_SUGGESTED_FOODS} Lebensmittel."
    ),
    "suggestions.twice": (
        "Ein Lebensmittel steht zweimal bei derselben Mahlzeit; entfernen Sie eines davon."
    ),
    "suggestions.full": f"Die Liste umfasst höchstens {config.MAX_SUGGESTED_FOODS} Lebensmittel.",
    "suggestions.total": (
        "Summe der Liste: {kcal} kcal, {protein} g Protein, {carbs} g Kohlenhydrate, {fat} g Fett."
    ),
    "suggestions.target": (
        "Die heutigen Ziele des Klienten: {kcal} kcal, {protein} g Protein, {carbs} g "
        "Kohlenhydrate, {fat} g Fett."
    ),
    "suggestions.no_target": "Der Klient hat heute keine Tagesziele.",
    "suggestions.share": (
        "In der gezeigten Woche hat der Klient {suggested} von {items} Lebensmitteln aus den "
        "Vorschlägen eines Coachs erfasst ({share} der Energie)."
    ),
    "suggestions.share_no_energy": (
        "In der gezeigten Woche hat der Klient {suggested} von {items} Lebensmitteln aus den "
        "Vorschlägen eines Coachs erfasst."
    ),
    "suggestions.share_none": "Der Klient hat in der gezeigten Woche keine Lebensmittel erfasst.",
    # Der Ernährungsplan des Coachs für einen Klienten (T11.7): ein Mustertag, für den Nutzer
    # nur zum Lesen.
    "meal_plan.coach_heading": "Ernährungsplan",
    "meal_plan.coach_intro": (
        "Ein Tag mit Mahlzeiten für diesen Klienten, gleich für jeden Tag. Jedes Speichern "
        "ersetzt den Plan und benachrichtigt den Klienten, der ihn auf seiner Seite "
        "Ernährungsplan liest, aber erfasst, was er wirklich isst. Die Tagessumme eines Plans "
        f"liegt nie unter {_FLOOR_DE} kcal, der Kaloriengrenze der App. Die App prüft keine "
        "Allergene oder Unverträglichkeiten: Fragen Sie Ihren Klienten danach."
    ),
    "meal_plan.not_shared": (
        "Ein Ernährungsplan kann nur festgelegt werden, solange der Klient die Ernährung teilt."
    ),
    "meal_plan.draft_empty": "Keine Lebensmittel im Plan.",
    "meal_plan.add_row": "Zum Plan hinzufügen",
    "meal_plan.remove_pick": "Aus dem Plan zu entfernendes Lebensmittel",
    "meal_plan.remove_row": "Aus dem Plan entfernen",
    "meal_plan.save": "Plan speichern",
    "meal_plan.saved": (
        "Der Ernährungsplan wurde gespeichert; der Klient sieht ihn auf seiner Seite "
        "Ernährungsplan."
    ),
    "meal_plan.remove_plan": "Plan entfernen",
    "meal_plan.removed": "Der Ernährungsplan wurde entfernt; der Klient sieht keinen mehr.",
    "meal_plan.refused": (
        "Der Plan wurde nicht gespeichert: Sie können für diesen Klienten jetzt keinen "
        "Ernährungsplan festlegen."
    ),
    "meal_plan.invalid": (
        f"Der Plan wurde nicht gespeichert: Geben Sie jedem Lebensmittel eine Mahlzeit und eine "
        f"Menge im erlaubten Bereich, höchstens {config.MAX_MEAL_PLAN_FOODS} Lebensmittel."
    ),
    "meal_plan.twice": (
        "Ein Lebensmittel steht zweimal bei derselben Mahlzeit; entfernen Sie eines davon."
    ),
    "meal_plan.full": f"Der Plan umfasst höchstens {config.MAX_MEAL_PLAN_FOODS} Lebensmittel.",
    "meal_plan.empty": (
        "Fügen Sie vor dem Speichern Lebensmittel hinzu, oder entfernen Sie den Plan mit seiner "
        "eigenen Schaltfläche."
    ),
    "meal_plan.below_floor": (
        f"Der Plan wurde nicht gespeichert: Seine Tagessumme liegt unter {_FLOOR_DE} kcal, der "
        "Kaloriengrenze der App. Fügen Sie zuerst Lebensmittel oder Gramm hinzu."
    ),
    "meal_plan.below_floor_draft": (
        f"Die Tagessumme liegt unter {_FLOOR_DE} kcal, der Kaloriengrenze der App, daher kann der "
        "Plan so nicht gespeichert werden."
    ),
    "meal_plan.meal_total": (
        "Summe {meal}: {kcal} kcal, {protein} g Protein, {carbs} g Kohlenhydrate, {fat} g Fett."
    ),
    "meal_plan.total": (
        "Tagessumme: {kcal} kcal, {protein} g Protein, {carbs} g Kohlenhydrate, {fat} g Fett."
    ),
    "meal_plan.gymer_intro": (
        "Der Ernährungsplan, den {coach} für Sie festgelegt hat: ein Tag mit Mahlzeiten, gleich "
        "für jeden Tag. Er ist ein Rat Ihres Coachs, hier zum Lesen; erfassen Sie unter Heute, "
        "was Sie wirklich essen."
    ),
    "meal_plan.not_checked": (
        "Das ist der Plan Ihres Coachs, nicht der App. Die App prüft ihn nicht auf Allergene oder "
        "Unverträglichkeiten und prüft die Qualifikationen eines Coachs nicht: Sagen Sie Ihrem "
        "Coach, wenn Sie eine Allergie haben, und wenden Sie sich für eine medizinische Diät an "
        "eine Ärztin oder einen Arzt."
    ),
    "meal_plan.saved_at": "Gespeichert am {when}.",
    "meal_plan.profile_first": (
        "Speichern Sie zuerst Ihre Angaben unter Mein Profil: Die App ist für Erwachsene, und Ihr "
        "Alter wird dort geprüft. Danach erscheint hier der Ernährungsplan Ihres Coachs."
    ),
    "meal_plan.none": "Ihr Coach hat noch keinen Ernährungsplan für Sie festgelegt.",
    "meal_plan.no_coach": (
        "Sie haben keinen Ernährungsplan. Ein Ernährungsplan kommt von dem Coach, mit dem Sie "
        "verbunden sind."
    ),
    "meal_plan.usda_note": (
        "Energie und Nährstoffe werden aus der USDA-Tabelle berechnet, als der Coach den Plan "
        "gespeichert hat."
    ),
    # Die Seite Heute: das Ernährungs- und Gewichtstagebuch (T9.13).
    "today.intro": (
        "Tragen Sie ein, was Sie gegessen haben, und Ihr Gewicht. Ein Tag ohne Einträge gilt als "
        "nicht eingetragen, nie als Tag ohne Essen."
    ),
    "today.made_up_only": (
        "Verwenden Sie nur erfundene Daten: Geben Sie keine echten Gesundheitsdaten ein."
    ),
    "today.profile_first": (
        "Speichern Sie zuerst Ihre Angaben unter Mein Profil (mit dem Häkchen, dass Sie verstehen, "
        "dass sie gespeichert werden). Danach können Sie hier Essen und Gewicht eintragen."
    ),
    "today.day": "Tag",
    "today.day_help": f"Heute oder bis zu {config.DIARY_MAX_DAYS_BACK} Tage zurück.",
    "today.add_food": "Lebensmittel hinzufügen",
    "today.food": "Lebensmittel",
    "today.food_placeholder": "Lebensmittel wählen",
    "today.grams": "Menge (g)",
    "today.meal": "Mahlzeit",
    "today.add": "Hinzufügen",
    "today.food_caption": (
        "Lebensmittel aus der USDA-Tabelle, auf Englisch. Jeder Eintrag behält die Nährwerte für "
        "die eingetragene Menge."
    ),
    "today.day_title": "Eingetragen am {day}",
    "today.nothing_logged": "An diesem Tag ist nichts eingetragen.",
    "today.meal_total": "**{meal}** · {kcal} kcal",
    "today.day_total": (
        "**Tagessumme:** {kcal} kcal · Protein {protein} g · Kohlenhydrate {carbohydrate} g · "
        "Fett {fat} g · Ballaststoffe {fiber}"
    ),
    "today.fiber_partial": "{value} g oder mehr (bei einigen Lebensmitteln nicht angegeben)",
    "today.col.food": "Lebensmittel",
    "today.col.grams": "Menge (g)",
    "today.col.kcal": "kcal",
    "today.col.protein": "Protein (g)",
    "today.col.carbohydrate": "Kohlenhydrate (g)",
    "today.col.fat": "Fett (g)",
    "today.col.fiber": "Ballaststoffe (g)",
    "today.edit_title": "Eintrag ändern oder löschen",
    "today.entry": "Eintrag",
    "today.entry_placeholder": "Eintrag wählen",
    "today.save_changes": "Änderungen speichern",
    "today.delete": "Eintrag löschen",
    "today.weight_title": "Gewicht",
    "today.weight_unit": "Gewicht ({unit})",
    "today.save_weight": "Gewicht speichern",
    "today.weights_logged": "An diesem Tag eingetragen: {weights}",
    "today.added": "Lebensmittel hinzugefügt.",
    "today.changed": "Eintrag geändert.",
    "today.deleted": "Eintrag gelöscht.",
    "today.weight_saved": "Gewicht gespeichert.",
    "today.gone": "Diesen Eintrag gibt es nicht mehr. Die Liste unten ist aktuell.",
    "today.stored_note": (
        "In der Datenbank dieser App gespeichert. Sie können es unter Meine Daten exportieren oder "
        "löschen; ein Coach sieht es nur, solange Sie Ernährung (Essen) oder Körper (Gewicht) mit "
        "dem Coach teilen."
    ),
    "diary.grams_range": (
        f"Geben Sie eine Menge von {plain(config.FOOD_MIN_GRAMS, 'de')} bis "
        f"{config.FOOD_MAX_GRAMS} g ein."
    ),
    "diary.meal_needed": "Wählen Sie eine Mahlzeit: Frühstück, Mittagessen, Abendessen oder Snack.",
    "diary.food_needed": "Wählen Sie ein Lebensmittel aus der Liste.",
    "diary.profile_first": (
        "Speichern Sie zuerst Ihre Angaben unter Mein Profil; hier wurde nichts gespeichert."
    ),
    "diary.food_table": (
        "Die Lebensmitteltabelle konnte nicht gelesen werden, daher wurde nichts gespeichert."
    ),
    "diary.day_range": (
        f"Wählen Sie heute oder einen Tag bis zu {config.DIARY_MAX_DAYS_BACK} Tage zurück."
    ),
    "diary.weight_range": (
        f"Geben Sie ein Gewicht von {plain(config.PROFILE_WEIGHT_KG_RANGE[0], 'de')} bis "
        f"{plain(config.PROFILE_WEIGHT_KG_RANGE[1], 'de')} kg ein (oder dasselbe in lb)."
    ),
}
