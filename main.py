import os
import random
import re
from difflib import SequenceMatcher

from flask import Flask, redirect, render_template, request, session, url_for


MAX_ATTEMPTS_PER_QUESTION = 2
MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 4


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")

def lav_spgliste():
	def newq(
		qid,
		difficulty,
		prompt,
		explanation,
		concept_groups,
	):
		points_by_difficulty = {1: 10, 2: 14, 3: 18, 4: 22}
		return {
			"qid": qid,
			"difficulty": difficulty,
			"prompt": prompt,
			"subject": f"{difficulty}. Klasse Matematik",
			"explanation": explanation,
			"points": points_by_difficulty[difficulty],
			"mode": "open",
			"concept_groups": concept_groups,
			"min_group_hits": 1,
		}



	return {			#klasse x spg x
		1: [
			newq(
				"K1Q1",
				1,
				"Kan man lave et tal, der aldrig stopper? Hvordan ville det se ud?",
				"Ja. Man kan blive ved med at lægge 1 til, så talrækken fortsætter uden slutning.",
				[["ja"], ["lægge 1 til", "plus 1", "blive ved"], ["uden slutning", "uendelig", "stopper aldrig"]],
			),
			newq(
				"K1Q2",
				1,
				"Find på dit eget mønster. Hvordan kan du være sikker på, at det er et mønster?",
				"Et mønster kræver en regel, som kan forklares og gentages.",
				[["regel"], ["forklare", "beskrive"], ["gentage", "fortsætte"]],
			),
		],
		2: [
			newq(
				"K2Q1",
				2,
				"Kan to forskellige regnestykker give det samme svar? Hvordan kan du finde flere?",
				"Ja, fx 3+3 og 2+4. Man kan lede systematisk efter flere.",
				[["ja"], ["samme svar", "samme resultat"], ["flere", "systematisk", "finde"]],
			),
			newq(
				"K2Q2",
				2,
				"Hvad sker der, hvis man ændrer én ting i et mønster?",
				"Hele mønsteret kan ændre sig.",
				[["mønster"], ["ændrer", "ændre sig"], ["hele", "sammenhæng", "påvirker"]],
			),
		],
		3: [
			newq(
				"K3Q1",
				3,
				"Kan man være sikker på, at man har fundet alle løsninger på et problem? Hvordan?",
				"Ikke altid. Man kan bruge systemer, fx starte fra 0 og arbejde opad.",
				[["ikke altid", "kan være svært"], ["system", "systematisk"], ["starte fra 0", "arbejde opad", "alle løsninger"]],
			),
			newq(
				"K3Q2",
				3,
				"Hvad er forskellen på at gætte og at vide noget i matematik?",
				"At vide kræver en forklaring eller begrundelse. At gætte er bare at komme med et svar uden grund.",
				[["gætte"], ["vide"], ["forklaring", "begrundelse", "argument"]],
			),
		],
		4: [
			newq(
				"K4Q1",
				4,
				"Find en regel, der virker for nogle tal, men ikke for alle. Hvorfor?",
				"Nogle regler virker kun for bestemte tal, fx lige tal. Det kan være fordi reglen er baseret på en egenskab, som ikke gælder for alle tal.",
				[["regel"], ["nogle tal", "ikke alle"], ["hvorfor", "modeksempel", "lige tal"]],
			),
			newq(
				"K4Q2",
				4,
				"Kan der være flere rigtige svar på det samme problem? Hvornår?",
				"Ja, især i åbne problemer eller ved forskellige metoder/definitioner.",
				[["ja"], ["flere rigtige svar", "forskellige svar"], ["åbent problem", "metoder", "definitioner"]],
			),
		],
	}


QUESTION_BANK = lav_spgliste()


def newstate():
	return {
		"started": True,
		"questions_answered": 0,
		"score": 0,
		"attempts": 0,
		"correctq": 0,
		"askedq": 0,
		"current_difficulty": 2,
		"correct_streak": 0,
		"wrong_streak": 0,
		"attempt": 1,
		"usedqid": [],
		"q": None,
		"feedback": None,
	}


def newprofile(existing=None):
	if existing:
		return existing
	return {
		"xp": 0,
		"sessions": 0,
		"totalanswrd": 0,
	}


def profile_level_info(total_xp):
	level = 1
	required_for_next = 80
	xp_remaining = total_xp

	while xp_remaining >= required_for_next:
		xp_remaining -= required_for_next
		level += 1
		required_for_next = int(required_for_next * 1.2)

	return {
		"level": level,
		"currentxp": xp_remaining,
		"xp_for_next": required_for_next,
	}


def calcxp(question, solved, attempt):
	if solved:
		base = max(6, question["points"] // 2)
		if attempt > 1:
			base = int(base * 0.75)
		return base
	return 1


def nyspg(state):
	pool = QUESTION_BANK[state["current_difficulty"]]
	used_ids = set(state["usedqid"])
	available_in_difficulty = [q for q in pool if q["qid"] not in used_ids]

	if available_in_difficulty:
		candidate_pool = available_in_difficulty
	else:
		all_questions = [q for questions in QUESTION_BANK.values() for q in questions]
		available_any = [q for q in all_questions if q["qid"] not in used_ids]
		if available_any:
			candidate_pool = available_any
		else:
			state["usedqid"] = []
			candidate_pool = pool

	question = random.choice(candidate_pool)
	state["usedqid"].append(question["qid"])
	state["q"] = question
	state["attempt"] = 1
	return question


def check_answer(question, user_input):
	answer_text = user_input.casefold().strip()
	answer_text = re.sub(r"[^\w\s]", "", answer_text)
	answer_text = answer_text.replace("_", " ")
	answer_text = re.sub(r"\s+", " ", answer_text)
	answer_words = answer_text.split()

	if not answer_words:
		return False, "Skriv lidt mere i dit svar"

	def fuzzy_match_word(target):
		target_stem = stem_word(target)
		for token in answer_words:
			token_stem = stem_word(token)
			if token_stem == target_stem:
				return True
			if token_stem.startswith(target_stem) or target_stem.startswith(token_stem):
				if min(len(token_stem), len(target_stem)) >= 3:
					return True
			if min(len(token_stem), len(target_stem)) <= 3:
				continue
			if SequenceMatcher(None, token_stem, target_stem).ratio() >= 0.84:	
				return True
		return False

	def stem_word(word):
		for suffix in ("erne", "ende", "ene", "ere", "ers", "er", "en", "et", "e", "s"):
			if word.endswith(suffix) and len(word) > len(suffix) + 2:
				return word[: -len(suffix)]
		return word

	def phrase_matches(phrase):
		phrase_text = phrase.casefold().strip()
		phrase_text = re.sub(r"[^\w\s]", "", phrase_text)
		phrase_text = phrase_text.replace("_", " ")
		phrase_text = re.sub(r"\s+", " ", phrase_text)
		if not phrase_text:
			return False
		if phrase_text in answer_text:
			return True
		parts = phrase_text.split()
		if len(parts) == 1:
			return fuzzy_match_word(parts[0])
		return all(fuzzy_match_word(part) for part in parts)

	if question["mode"] in {"open", "keywords"}:
		group_hits = 0
		for group in question.get("concept_groups", []):
			if any(phrase_matches(option) for option in group):
				group_hits += 1

		min_hits = int(question.get("min_group_hits", 1))
		if group_hits >= min_hits:
			return True, "Korrekt"

		return False, "Svar for kort eller uden tydelige faglige elementer"

	return False, "Forkert (ukendt evalueringsmetode)"


def updatediff(state, solved):
	previous = state["current_difficulty"]

	if solved:
		state["correct_streak"] += 1
		state["wrong_streak"] = 0
		if state["correct_streak"] >= 2 and state["current_difficulty"] < MAX_DIFFICULTY:
			state["current_difficulty"] += 1
			state["correct_streak"] = 0
	else:
		state["wrong_streak"] += 1
		state["correct_streak"] = 0
		if state["wrong_streak"] >= 2 and state["current_difficulty"] > MIN_DIFFICULTY:
			state["current_difficulty"] -= 1
			state["wrong_streak"] = 0

	if state["current_difficulty"] > previous:
		return f"Sværhedsgrad opjusteret til {state['current_difficulty']}."
	if state["current_difficulty"] < previous:
		return f"Sværhedsgrad nedjusteret til {state['current_difficulty']}."
	return f"Sværhedsgrad fastholdt på {state['current_difficulty']}."


def correctpercent(state):
	if state["askedq"] == 0:
		return 0.0
	return (state["correctq"] / state["askedq"]) * 100


@app.get("/")
def landing() -> str:
	state = session.get("game_state")
	profile = newprofile(session.get("profile_state"))
	level_info = profile_level_info(profile["xp"])
	has_active_session = bool(state and state.get("started", False))
	session["profile_state"] = profile
	return render_template(
		"landing.html",
		has_active_session=has_active_session,
		profile=profile,
		profile_level=level_info,
	)


@app.get("/play")
def play() -> str:
	state = session.get("game_state")
	profile = newprofile(session.get("profile_state"))
	level_info = profile_level_info(profile["xp"])
	if not state:
		return render_template(
			"game.html",
			state=None,
			max_attempts=MAX_ATTEMPTS_PER_QUESTION,
			accuracy=0.0,
			profile=profile,
			profile_level=level_info,
		)

	if not state["q"]:
		nyspg(state)
		session["game_state"] = state

	session["profile_state"] = profile
	return render_template(
		"game.html",
		state=state,
		max_attempts=MAX_ATTEMPTS_PER_QUESTION,
		accuracy=round(correctpercent(state), 1),
		profile=profile,
		profile_level=level_info,
	)


@app.post("/start")
def start_game():
	state = newstate()
	profile = newprofile(session.get("profile_state"))
	profile["sessions"] += 1
	nyspg(state)
	session["game_state"] = state
	session["profile_state"] = profile
	return redirect(url_for("play"))


@app.post("/answer")
def submit_answer():
	state = session.get("game_state")
	profile = newprofile(session.get("profile_state"))
	if not state or not state["q"]:
		return redirect(url_for("play"))

	user_answer = request.form.get("answer", "").strip()
	if not user_answer:
		state["feedback"] = {
			"ok": False,
			"message": "Skriv et svar, før du afleverer.",
			"details": "Dit forsøg er ikke brugt. Skriv et lidt længere svar.",
			"awarded": 0,
			"xp_gain": 0,
			"short_input": True,
		}
		session["game_state"] = state
		return redirect(url_for("play"))

	question = state["q"]
	is_correct, message = check_answer(question, user_answer)
	is_too_short = message in {
		"Skriv lidt mere i dit svar",
		"Svar for kort eller uden tydelige faglige elementer",
	}

	if is_too_short:
		state["feedback"] = {
			"ok": False,
			"message": "Svar for kort",
			"details": "Dit forsøg er ikke brugt. Skriv lidt mere uddybende.",
			"awarded": 0,
			"xp_gain": 0,
			"short_input": True,
		}
		session["game_state"] = state
		session["profile_state"] = profile
		return redirect(url_for("play"))

	state["attempts"] += 1

	if is_correct:
		xp_gain = calcxp(question, solved=True, attempt=state["attempt"])
		awarded = question["points"]
		if state["attempt"] > 1:
			awarded = int(question["points"] * 0.7)
		state["score"] += awarded
		profile["xp"] += xp_gain
		state["correctq"] += 1
		state["askedq"] += 1
		state["questions_answered"] += 1
		profile["totalanswrd"] += 1
		updatediff(state, solved=True)

		state["feedback"] = {
			"ok": True,
			"message": message,
			"details": question['explanation'],
			"awarded": awarded,
			"xp_gain": xp_gain,
			"short_input": False,
		}
		state["q"] = None
		state["attempt"] = 1
	else:
		if state["attempt"] < MAX_ATTEMPTS_PER_QUESTION:
			state["attempt"] += 1
			state["feedback"] = {
				"ok": False,
				"message": message,
				"details": f"{question['explanation']} Du har {MAX_ATTEMPTS_PER_QUESTION - state['attempt'] + 1} forsøg tilbage.",
				"awarded": 0,
				"xp_gain": 0,
				"short_input": False,
			}
		else:
			xp_gain = calcxp(question, solved=False, attempt=state["attempt"])
			state["askedq"] += 1
			state["questions_answered"] += 1
			profile["totalanswrd"] += 1
			profile["xp"] += xp_gain
			updatediff(state, solved=False)
			state["feedback"] = {
				"ok": False,
				"message": "Forkert",
				"details": f"{question['explanation']} Ingen flere forsøg på denne opgave.",
				"awarded": 0,
				"xp_gain": xp_gain,
				"short_input": False,
			}
			state["q"] = None
			state["attempt"] = 1

	if not state["q"]:
		nyspg(state)

	session["game_state"] = state
	session["profile_state"] = profile
	return redirect(url_for("play"))


@app.post("/skip")
def skip_question():
	state = session.get("game_state")
	if not state or not state.get("q"):
		return redirect(url_for("play"))

	state["q"] = None
	state["attempt"] = 1
	state["feedback"] = {
		"ok": False,
		"message": "Spørgsmål sprunget over",
		"details": "Nyt spørgsmål valgt.",
		"awarded": 0,
		"xp_gain": 0,
		"short_input": False,
	}
	nyspg(state)
	session["game_state"] = state
	return redirect(url_for("play"))


@app.post("/reset")
def reset_game():
	session.pop("game_state", None)
	return redirect(url_for("landing"))


@app.post("/test/reset-level")
def test_reset_level():
	profile = newprofile(session.get("profile_state"))
	profile["xp"] = 0
	session["profile_state"] = profile
	return redirect(url_for("landing"))


@app.post("/test/give-xp")
def test_give_xp():
	profile = newprofile(session.get("profile_state"))
	profile["xp"] += 50
	session["profile_state"] = profile
	return redirect(url_for("landing"))


if __name__ == "__main__":
	app.run(debug=True)
