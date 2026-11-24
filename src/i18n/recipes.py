"""The texts of the coach's Recipe library and the gymer's Recipes page (T11.8)."""

from src import config
from src.i18n.core import plain

_MIN = config.RATING_MIN_RATERS
_NAME = config.RECIPE_NAME_MAX_CHARS
_STEPS = f"{config.RECIPE_STEPS_MAX_CHARS:,}"
_FOODS = config.MAX_RECIPE_INGREDIENTS
_RECIPES = config.MAX_RECIPES_PER_COACH
# The portion range as the picker shows it ("0.25" to "3", "0,25" bis "3").
_LOW, _HIGH = (plain(bound, "en") for bound in config.RECIPE_PORTION_RANGE)
_LOW_DE, _HIGH_DE = (plain(bound, "de") for bound in config.RECIPE_PORTION_RANGE)

EN: dict[str, str] = {
    "page.recipe_library": "Recipe library",
    "page.recipes": "Recipes",
    # The coach's Recipe library.
    "recipes.coach_intro": (
        "Your own recipes: a name, foods from the USDA table with grams, and the steps in your own "
        "words. The clients you are connected with now see them and log one in a click; a client "
        f"who logged a recipe can rate it from 1 to 5 stars. You see a recipe's average only once "
        f"at least {_MIN} clients who share nutrition with you have rated it, and never who rated. "
        "Recipes are stored in this app's data file on this computer and are not sent to the AI. "
        "Every client you are connected with sees every recipe: do not name a client or write "
        "about anyone's health in it."
    ),
    "recipes.coach_not_checked": (
        "The app does not check a recipe for allergens or intolerances, nor a coach's "
        "qualifications, and your clients are told so."
    ),
    "recipes.none_coach": "You have no recipes yet.",
    "recipes.new": "New recipe",
    "recipes.editing": "Edit: {name}",
    "recipes.name": "Name",
    "recipes.steps": "Steps",
    "recipes.steps_help": (
        f"In your own words, up to {_STEPS} characters. Markdown formatting (bold, lists) works; "
        "images and links show as plain text."
    ),
    "recipes.foods": "Foods",
    "recipes.draft_empty": "No foods in the recipe yet.",
    "recipes.add_food": "Add to the recipe",
    "recipes.remove_pick": "Food to take out",
    "recipes.remove_food": "Take out",
    "recipes.save": "Save the recipe",
    "recipes.cancel": "Cancel",
    "recipes.edit": "Edit",
    "recipes.delete": "Delete",
    "recipes.delete_confirm": (
        "Delete this recipe with its ratings? Meals your clients logged from it stay in their "
        "diaries. This cannot be undone."
    ),
    "recipes.delete_yes": "Delete for good",
    "recipes.delete_no": "Keep it",
    "recipes.saved": "Recipe saved.",
    "recipes.deleted": "Recipe deleted.",
    "recipes.refused": "This recipe can no longer be changed.",
    "recipes.invalid": "The recipe could not be saved. Check its name, steps and foods.",
    "recipes.rating_line": "Rated {average} of 5 by {count} clients.",
    "recipes.rating_not_enough": "Not enough ratings yet.",
    "recipes.rating_note_coach": (
        f"Only ratings of clients who share nutrition with you count, from {_MIN} of them."
    ),
    # Shared by both pages.
    "recipes.food_line": "{food}: {grams} g, {kcal} kcal",
    "recipes.total": (
        "Total: {kcal} kcal, {protein} g protein, {carbs} g carbohydrate, {fat} g fat."
    ),
    "recipes.usda_note": (
        "Energy and nutrients are worked out from the USDA table when the coach saved the recipe."
    ),
    # The gymer's Recipes page.
    "recipes.gymer_intro": (
        "Recipes by {coach}, shared with all their clients. Log one in a click at its own "
        "amounts, or choose a "
        "portion: each food goes into your diary for the day and meal you pick, marked as from "
        "this recipe. After you have logged a recipe you can rate it."
    ),
    "recipes.gymer_not_checked": (
        "These are your coach's recipes, not the app's. The app does not check them for allergens "
        "or intolerances, and does not check a coach's qualifications: tell your coach about any "
        "allergy, and see a doctor for a medical diet."
    ),
    "recipes.profile_first": (
        "Save your details on My profile first: the app is for adults, and your age is checked "
        "there. Then your coach's recipes show here."
    ),
    "recipes.no_coach": (
        "You have no recipes. Recipes come from the coach you are connected with."
    ),
    "recipes.none_gymer": "Your coach has not written any recipes yet.",
    "recipes.day": "Day",
    "recipes.meal": "Meal",
    "recipes.portion": "Portion",
    "recipes.portion_help": (
        f"1 is the recipe's own amounts; from {_LOW} to {_HIGH} times them, every food alike."
    ),
    "recipes.log": "Log this recipe",
    "recipes.logged": "Recipe logged.",
    "recipes.rate": "Your rating",
    "recipes.rated": "Rating saved.",
    "recipes.rate_after_log": "Log this recipe to rate it.",
    "recipes.rating_counts_note": (
        "Your coach sees only the average and the number of ratings, never yours alone, and only "
        "while you share nutrition with them. With few clients your coach may still work out "
        "your rating, for example from how the average changes after you rate. Your rating is "
        "deleted if your coach deletes the recipe or their account."
    ),
    # Errors (the codes of diary.DiaryError).
    "recipes.twice": "That food is already in the recipe; change its grams instead.",
    "recipes.name_needed": "Give the recipe a name.",
    "recipes.steps_needed": "Write the recipe's steps.",
    "recipes.too_long": (
        f"Keep the name to {_NAME} characters and the steps to {_STEPS} characters."
    ),
    "recipes.empty": "Add at least one food to the recipe.",
    "recipes.full": f"A recipe holds at most {_FOODS} foods.",
    "recipes.too_many": f"You can keep at most {_RECIPES} recipes; delete one first.",
    "recipes.portion_range": f"Choose a portion from {_LOW} to {_HIGH}.",
    "recipes.gone": (
        "This recipe is no longer available: your coach deleted it, or you are no longer connected."
    ),
    "recipes.scaled_grams": (
        "At this portion a food would be outside the diary's gram range; choose another portion."
    ),
    "recipes.stars": "Choose from 1 to 5 stars.",
    "recipes.cannot_rate": "You can rate only a recipe of your coach that you have logged.",
}

DE: dict[str, str] = {
    "page.recipe_library": "Rezeptsammlung",
    "page.recipes": "Rezepte",
    "recipes.coach_intro": (
        "Ihre eigenen Rezepte: ein Name, Lebensmittel aus der USDA-Tabelle mit Grammangaben und "
        "die Zubereitung in Ihren eigenen Worten. Die Klienten, mit denen Sie jetzt verbunden "
        "sind, sehen sie und erfassen eines mit einem Klick; wer ein Rezept erfasst hat, kann es "
        f"mit 1 bis 5 Sternen bewerten. Den Durchschnitt eines Rezepts sehen Sie erst, wenn "
        f"mindestens {_MIN} Klienten, die ihre Ernährung mit Ihnen teilen, es bewertet haben, und "
        "nie, wer bewertet hat. Rezepte werden in der Datendatei dieser App auf diesem Computer "
        "gespeichert und nicht an die KI gesendet. Jeder Klient, mit dem Sie verbunden sind, sieht "
        "jedes Rezept: Nennen Sie darin keinen Klienten und schreiben Sie nichts über die "
        "Gesundheit von jemandem."
    ),
    "recipes.coach_not_checked": (
        "Die App prüft Rezepte nicht auf Allergene oder Unverträglichkeiten und prüft die "
        "Qualifikationen eines Coachs nicht; Ihre Klienten werden darauf hingewiesen."
    ),
    "recipes.none_coach": "Sie haben noch keine Rezepte.",
    "recipes.new": "Neues Rezept",
    "recipes.editing": "Bearbeiten: {name}",
    "recipes.name": "Name",
    "recipes.steps": "Zubereitung",
    "recipes.steps_help": (
        f"In Ihren eigenen Worten, bis zu {_STEPS.replace(',', '.')} Zeichen. Markdown "
        "(fett, Listen) funktioniert; Bilder und Links erscheinen als einfacher Text."
    ),
    "recipes.foods": "Lebensmittel",
    "recipes.draft_empty": "Noch keine Lebensmittel im Rezept.",
    "recipes.add_food": "Zum Rezept hinzufügen",
    "recipes.remove_pick": "Lebensmittel zum Entfernen",
    "recipes.remove_food": "Entfernen",
    "recipes.save": "Rezept speichern",
    "recipes.cancel": "Abbrechen",
    "recipes.edit": "Bearbeiten",
    "recipes.delete": "Löschen",
    "recipes.delete_confirm": (
        "Dieses Rezept mit seinen Bewertungen löschen? Mahlzeiten, die Ihre Klienten damit "
        "erfasst haben, bleiben in deren Tagebuch. Das lässt sich nicht rückgängig machen."
    ),
    "recipes.delete_yes": "Endgültig löschen",
    "recipes.delete_no": "Behalten",
    "recipes.saved": "Rezept gespeichert.",
    "recipes.deleted": "Rezept gelöscht.",
    "recipes.refused": "Dieses Rezept kann nicht mehr geändert werden.",
    "recipes.invalid": (
        "Das Rezept konnte nicht gespeichert werden. Prüfen Sie Name, Zubereitung und Lebensmittel."
    ),
    "recipes.rating_line": "Von {count} Klienten mit {average} von 5 Sternen bewertet.",
    "recipes.rating_not_enough": "Noch nicht genug Bewertungen.",
    "recipes.rating_note_coach": (
        f"Es zählen nur Bewertungen von Klienten, die ihre Ernährung mit Ihnen teilen, ab {_MIN} "
        "von ihnen."
    ),
    "recipes.food_line": "{food}: {grams} g, {kcal} kcal",
    "recipes.total": (
        "Summe: {kcal} kcal, {protein} g Protein, {carbs} g Kohlenhydrate, {fat} g Fett."
    ),
    "recipes.usda_note": (
        "Energie und Nährstoffe werden aus der USDA-Tabelle berechnet, als der Coach das Rezept "
        "gespeichert hat."
    ),
    "recipes.gymer_intro": (
        "Rezepte von {coach}, für alle Klienten gleich. Erfassen Sie eines mit einem Klick in "
        "seinen eigenen Mengen oder wählen Sie eine Portion: Jedes Lebensmittel kommt für den Tag "
        "und die Mahlzeit, die Sie wählen, in Ihr Tagebuch, als aus diesem Rezept markiert. Wenn "
        "Sie ein Rezept erfasst haben, können Sie es bewerten."
    ),
    "recipes.gymer_not_checked": (
        "Das sind die Rezepte Ihres Coachs, nicht der App. Die App prüft sie nicht auf Allergene "
        "oder Unverträglichkeiten und prüft die Qualifikationen eines Coachs nicht: Sagen Sie "
        "Ihrem Coach, wenn Sie eine Allergie haben, und wenden Sie sich für eine medizinische Diät "
        "an eine Ärztin oder einen Arzt."
    ),
    "recipes.profile_first": (
        "Speichern Sie zuerst Ihre Angaben unter Mein Profil: Die App ist für Erwachsene, und Ihr "
        "Alter wird dort geprüft. Danach erscheinen hier die Rezepte Ihres Coachs."
    ),
    "recipes.no_coach": (
        "Sie haben keine Rezepte. Rezepte kommen von dem Coach, mit dem Sie verbunden sind."
    ),
    "recipes.none_gymer": "Ihr Coach hat noch keine Rezepte geschrieben.",
    "recipes.day": "Tag",
    "recipes.meal": "Mahlzeit",
    "recipes.portion": "Portion",
    "recipes.portion_help": (
        f"1 sind die Mengen des Rezepts; von {_LOW_DE} bis "
        f"{_HIGH_DE} mal so viel, alle Lebensmittel gleich."
    ),
    "recipes.log": "Dieses Rezept erfassen",
    "recipes.logged": "Rezept erfasst.",
    "recipes.rate": "Ihre Bewertung",
    "recipes.rated": "Bewertung gespeichert.",
    "recipes.rate_after_log": "Erfassen Sie dieses Rezept, um es zu bewerten.",
    "recipes.rating_counts_note": (
        "Ihr Coach sieht nur den Durchschnitt und die Anzahl der Bewertungen, nie Ihre einzelne "
        "Bewertung, "
        "und nur, solange Sie Ihre Ernährung mit Ihrem Coach teilen. Bei wenigen Klienten kann er "
        "Ihre Bewertung trotzdem erschließen, zum Beispiel daraus, wie sich der Durchschnitt nach "
        "Ihrer Bewertung ändert. Ihre Bewertung wird gelöscht, wenn Ihr Coach das Rezept oder "
        "das eigene Konto löscht."
    ),
    "recipes.twice": (
        "Dieses Lebensmittel ist schon im Rezept; ändern Sie stattdessen seine Grammangabe."
    ),
    "recipes.name_needed": "Geben Sie dem Rezept einen Namen.",
    "recipes.steps_needed": "Schreiben Sie die Zubereitung des Rezepts.",
    "recipes.too_long": (
        f"Der Name darf höchstens {_NAME} Zeichen haben, die Zubereitung höchstens "
        f"{_STEPS.replace(',', '.')} Zeichen."
    ),
    "recipes.empty": "Fügen Sie dem Rezept mindestens ein Lebensmittel hinzu.",
    "recipes.full": f"Ein Rezept enthält höchstens {_FOODS} Lebensmittel.",
    "recipes.too_many": (
        f"Sie können höchstens {_RECIPES} Rezepte behalten; löschen Sie zuerst eines."
    ),
    "recipes.portion_range": (f"Wählen Sie eine Portion von {_LOW_DE} bis {_HIGH_DE}."),
    "recipes.gone": (
        "Dieses Rezept ist nicht mehr verfügbar: Ihr Coach hat es gelöscht, oder Sie sind nicht "
        "mehr verbunden."
    ),
    "recipes.scaled_grams": (
        "Bei dieser Portion läge ein Lebensmittel außerhalb des Grammbereichs des Tagebuchs; "
        "wählen Sie eine andere Portion."
    ),
    "recipes.stars": "Wählen Sie 1 bis 5 Sterne.",
    "recipes.cannot_rate": (
        "Sie können nur ein Rezept Ihres Coachs bewerten, das Sie erfasst haben."
    ),
}
