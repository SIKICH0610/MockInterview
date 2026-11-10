"""Question bank seeded from the official TK / K Ticket question cards.

Rubric texts are taken verbatim from the decks' TEACHER USE ONLY
GUIDE / SCORE pages, so the workbench shows the real 0/1/2 criteria
next to every task.
"""

from .models import AssessSession, Paper, Question

# Shared academic rubric for the five mathematics tasks (M02-M06)
MATH_R = {
    "r2": "Independent correct answer",
    "r1": "Correct after guidance",
    "r0": "No correct answer after guidance",
}
# Shared oral expression rubric observed across M02-M06
EXPR = {
    "e2": "Relevant complete sentence",
    "e1": "Relevant word / short phrase",
    "e0": "No relevant oral response",
}
# M01 Creativity ticket rubric (no expression score by design)
M01_R = {
    "r2": "Extra decoration beyond the required number-writing",
    "r1": "Prescribed number-writing / drawing only",
    "r0": "No drawing or writing",
}

# Story Time: the 8 "LET'S TALK" response opportunities in Pip's Picnic Helpers
STORY_PROMPTS = [
    "Who do you notice? You can point or tell me.",
    "What would you bring to a picnic?",
    "What happened to the blanket?",
    "What could a friend say to Pip?",
    "How are the friends helping?",
    "How can we show Turtle that we are listening?",
    "Would you like to make a ticket with us?",
    "Tell us or show us one thing about your ticket or your picnic idea.",
]

STAGES = [
    "Separation",
    "Self Introduction",
    "Story Time",
    "Cutting & Drawing",
    "Station",
    "Other",
]

# Multi-dimension observation rubric for the group activities,
# digitized from the legacy paper "Group" scoring sheet.
# Three tiers per dimension (best / middle / weakest): four-tier scales
# made the two middle options too vague to choose between.
_HANDCRAFT_DIMS = [
    ("follow", "Follow Instruction", ["Always", "Need Reminder", "Cannot Follow"]),
    ("motor", "Fine Motor Skills", ["Good", "Fair", "Needs Support"]),
    ("sharing", "Sharing Tool", ["Good", "Fair", "Cannot Share"]),
    ("problem", "Problem Solving", ["Good", "Fair", "Cannot Solve"]),
    ("creativity", "Creativity", ["Design Sth New", "Similar to Example", "Same as Example"]),
    ("attitude", "General Attitude", ["Good", "Fair", "Passive"]),
]

_SELF_INTRO_DIMS = [  # legacy sheet: Self Introduction block
    ("initiative", "Initiative to Participate (Raise Hand)", ["Yes", "No"]),
    ("confidence", "Confidence", ["Confident", "A Little Nervous", "Very Nervous"]),
    ("fluency", "Expression Fluency", ["Fluent", "Limited Fluency", "Cannot Complete"]),
    ("listen", "Listen to Others", ["Good", "Fair", "Cannot Focus"]),
]

STAGE_DIMS = {
    "Self Introduction": _SELF_INTRO_DIMS,
    "Story Time": [
        ("participation", "Participation", ["Active", "Moderately Engaged", "Disengaged"]),
        ("focus", "Focus", ["Good", "Fair", "Cannot Focus"]),
        ("listen", "Listen to Others", ["Always", "Need Reminder", "Cannot Listen"]),
        ("empathy", "Empathy", ["Good", "Fair", "Limited"]),
    ],
    "Cutting & Drawing": _HANDCRAFT_DIMS,
}


def _q(version, code, sort, domain, ability, title, prompt, target, setup, r, e=None, trial_max=None):
    return dict(
        version=version,
        code=code,
        sort=sort,
        domain=domain,
        ability=ability,
        title=title,
        prompt=prompt,
        target=target,
        setup=setup,
        r2=r["r2"],
        r1=r["r1"],
        r0=r["r0"],
        e2=e["e2"] if e else None,
        e1=e["e1"] if e else None,
        e0=e["e0"] if e else None,
        has_expression=bool(e),
        trial_max=trial_max,
    )


QUESTIONS = [
    # ---------------- TK ----------------
    _q("TK", "M01", 1, "Mathematics", "Creativity",
       "Make Pip's picnic ticket",
       "Write 1 in the circle, 2 in the triangle and 3 in the square.",
       "Completed during the group activity after the story; the child brings the ticket to the station.",
       "The station teacher observes the existing work and records M01 once. Do not ask the child to remake or explain it. Digit accuracy is noted but is not a separate academic score.",
       M01_R),
    _q("TK", "M02", 2, "Mathematics", "Number Sense",
       "Share the cakes",
       "I have 4 cakes. I give away 2. How many are left?",
       "4 cakes, give away 2; 2 remain.",
       "Cut apart the cake pieces before M02. Offer all four cake pieces before the first response.",
       MATH_R, EXPR),
    _q("TK", "M03", 3, "Mathematics", "Measurement & Data",
       "Look at the balance",
       "Which object is heavier? Which is lighter?",
       "The bear is heavier; the ball is lighter. Use the lower balance pan as evidence, not object size.",
       "",
       MATH_R, EXPR),
    _q("TK", "M04", 4, "Mathematics", "Spatial Sense",
       "Complete the dinosaur picture",
       "Put the pieces back.",
       "Place the triangle, circle and rectangular picture pieces in their matching image gaps.",
       "Offer all pieces; do not pre-place them.",
       MATH_R, EXPR),
    _q("TK", "M05", 5, "Mathematics", "Reasoning",
       "Finish the fruit pattern",
       "Add the next three pieces.",
       "Continue the apple, pear, banana repeating unit.",
       "Offer loose picture pieces without naming the unit.",
       MATH_R, EXPR),
    _q("TK", "M06", 6, "Mathematics", "Critical Thinking",
       "Help Teddy stay dry",
       "Teddy is getting wet. What could help?",
       "A workable solution, such as the umbrella. Accept another sensible solution supported by the picture.",
       "Score the two aspects independently: a correct nonverbal solution may earn academic points with expression 0; a clear sentence with an incorrect answer may earn expression points with academic 0.",
       MATH_R, EXPR),
    _q("TK", "E01", 7, "English", "Letter Names",
       "Name the letters",
       "What letter is this?  —  B · h · L · q · R · y",
       "Names the six mixed-case letters.",
       "Point one at a time. Save the initial correct count /6 and record reversals. Ask names, not sounds.",
       {"r2": "Independently names all 6 letters: B, h, L, q, R, y",
        "r1": "Independently names 1–5, or reaches more after a letter cue",
        "r0": "No target letter name is established after support"},
       trial_max=6),
    _q("TK", "E02", 8, "English", "Letter Sounds",
       "Say the letter sounds",
       "What sound does this letter make?  —  f · I · m · S · u · V",
       "Targets: f /f/, I short i, m /m/, S /s/, u short u, V /v/.",
       "Point one at a time. Letter names alone do not count. Accept accent variation; save count /6.",
       {"r2": "Independently produces all six target letter sounds",
        "r1": "Produces 1–5 target sounds independently, or more after sound cues",
        "r0": "No target sound is established after support"},
       trial_max=6),
    _q("TK", "E03", 9, "English", "CVC Reading",
       "Read the words",
       "Can you read these words?  —  cat · pen · dog",
       "Decodes the three CVC words.",
       "Allow self-initiated sounding out and blending. None of these words uses a letter from E01 or E02. Save independent whole-word count /3.",
       {"r2": "Independently decodes all 3 words: cat, pen, dog",
        "r1": "Independently decodes some of the words, or blends successfully after an adult sound cue",
        "r0": "No whole printed word is established after support"},
       trial_max=3),
    _q("TK", "E04", 10, "English", "Sentence Reading",
       "Read the sentence",
       "Read this aloud.  —  We see a fish.",
       "Reads the sentence with recognizable words.",
       "Do not model the sentence first. Self-correction and sounding out are allowed. The sentence words do not repeat the three word-reading items.",
       {"r2": "Independently reads the complete sentence with recognizable words",
        "r1": "Reads some relevant printed words independently, or completes after a word cue",
        "r0": "No recognizable printed word is read after support"}),
    _q("TK", "E05", 11, "English", "Opposite Words",
       "Tell me the opposite",
       "The rabbit is fast. What is the opposite of fast?",
       "Says “slow”.",
       "Teacher may read the prompt aloud. No sentence reading is required here. Accept a recognizable word; do not model the opposite before the first attempt.",
       {"r2": "Independently says “slow”",
        "r1": "Shows the opposite action / chooses the picture without the English word, or gives the word after a cue",
        "r0": "No appropriate opposite is established after support"}),
    _q("TK", "E06", 12, "English", "Classification",
       "Sort the animals",
       "Which live in the sea? Which live on land?",
       "Dolphin, octopus, shark = sea; lion, elephant, horse = land.",
       "Read the group labels before the child sorts; naming each animal is not required. Save initial placement count /6.",
       {"r2": "Independently sorts all 6 pictures into the two requested groups",
        "r1": "Independently sorts 1–5 correctly, or completes the groups after a category cue",
        "r0": "No valid category placement is established after support"},
       trial_max=6),

    # ---------------- K ----------------
    _q("K", "M01", 1, "Mathematics", "Creativity",
       "Make Pip's picnic ticket",
       "Write 1 in the circle, 2 in the triangle and 3 in the square.",
       "Completed during the group activity after the story; the child brings the ticket to the station.",
       "The station teacher observes the existing work and records M01 once. Do not ask the child to remake or explain it. Digit accuracy is noted but is not a separate academic score.",
       M01_R),
    _q("K", "M02", 2, "Mathematics", "Number Sense",
       "Which color has more?",
       "Which color has more apples? How many more?",
       "Red has more; there are 2 more red apples (7 red, 5 green). Both parts are required for a complete answer.",
       "Align the rows without pre-counting them (red on top, green below, both starting from the left).",
       MATH_R, EXPR),
    _q("K", "M03", 3, "Mathematics", "Measurement & Data",
       "Compare the ropes",
       "Which rope is longer?",
       "The orange rope has the greater path length. The number of curves alone is not the answer.",
       "Do not suggest a measuring method.",
       MATH_R, EXPR),
    _q("K", "M04", 4, "Mathematics", "Spatial Sense",
       "Look at what is in front",
       "Which toy is in front? Which toy is at the back?",
       "Red ball in front, dinosaur at the back.",
       "Do not explain the covered edges before the first attempt.",
       MATH_R, EXPR),
    _q("K", "M05", 5, "Mathematics", "Reasoning",
       "Finish the bead necklace",
       "Which colors belong in the two empty places?",
       "Use the circular ABC sequence to fill the two missing beads.",
       "There is no arrow or marked starting point. Cut apart the bead pieces before M05 and offer all colors.",
       MATH_R, EXPR),
    _q("K", "M06", 6, "Mathematics", "Critical Thinking",
       "Which one is different?",
       "Choose one that is different. Show or tell me why.",
       "Chooses an item and gives a valid distinction, through words, pointing or demonstration. Several answers are possible.",
       "Do not require a single preset choice. Score the two aspects independently: a correct nonverbal solution may earn academic points with expression 0, and vice versa.",
       MATH_R, EXPR),
    _q("K", "E01", 7, "English", "Letter Names",
       "Name the letters",
       "What letter is this?  —  B · h · L · q · J · y",
       "Names the six mixed-case letters.",
       "Point one at a time. Save the initial correct count /6 and record reversals. Ask names, not sounds.",
       {"r2": "Independently names all 6 letters: B, h, L, q, J, y",
        "r1": "Independently names 1–5, or reaches more after a letter cue",
        "r0": "No target letter name is established after support"},
       trial_max=6),
    _q("K", "E02", 8, "English", "Letter Sounds",
       "Say the letter sounds",
       "What sound does this letter make?  —  f · O · m · S · u · V",
       "Targets: f /f/, O short o, m /m/, S /s/, u short u, V /v/.",
       "Point one at a time. Letter names alone do not count. Accept accent variation; save count /6.",
       {"r2": "Independently produces all six target letter sounds",
        "r1": "Produces 1–5 target sounds independently, or more after sound cues",
        "r0": "No target sound is established after support"},
       trial_max=6),
    _q("K", "E03", 9, "English", "Blends & CVCE Reading",
       "Read the words",
       "Can you read these words?  —  cat · trip · cake",
       "Decodes cat (CVC), trip (CCVC), cake (CVCE).",
       "Allow self-initiated sounding out and blending. None of these words uses a letter from E01 or E02. Save independent whole-word count /3.",
       {"r2": "Independently decodes all 3 words: cat, trip, cake",
        "r1": "Independently decodes some of the words, or blends successfully after an adult sound cue",
        "r0": "No whole printed word is established after support"},
       trial_max=3),
    _q("K", "E04", 10, "English", "Sentence Reading",
       "Read the sentences",
       "Read each sentence aloud.  —  We see a fish. / My red hat is big. / You like blue cups.",
       "Reads the three sentences with recognizable words.",
       "Do not model the sentences first. Self-correction and sounding out are allowed. Save sentence-level results /3 as well as word-level notes.",
       {"r2": "Independently reads all 3 complete sentences with recognizable words",
        "r1": "Reads 1–2 complete sentences, some words independently, or completes after a word cue",
        "r0": "No recognizable printed word is read after support"},
       trial_max=3),
    _q("K", "E05", 11, "English", "Opposite Words",
       "Tell me the opposite",
       "What is the opposite of push?",
       "Says “pull”.",
       "Teacher may read the prompt aloud. No sentence reading is required here. Accept a recognizable word; do not model the opposite before the first attempt.",
       {"r2": "Independently says “pull”",
        "r1": "Shows the opposite action / chooses the picture without the English word, or gives the word after a cue",
        "r0": "No appropriate opposite is established after support"}),
    _q("K", "E06", 12, "English", "Classification",
       "Sort the clothes",
       "Which clothes are for a cold winter? Which are for a hot summer?",
       "Coat, wool hat, mittens = cold winter; shorts, T-shirt, sandals = hot summer.",
       "Read the group labels before the child sorts; naming each garment is not required. Save initial placement count /6.",
       {"r2": "Independently sorts all 6 pictures into the two requested groups",
        "r1": "Independently sorts 1–5 correctly, or completes the groups after a category cue",
        "r0": "No valid category placement is established after support"},
       trial_max=6),
]


def seed_questions(db):
    paper = db.query(Paper).order_by(Paper.id).first()
    if paper is None:
        paper = Paper(name="TK/K Ticket Edition v1", note="Seeded from the official TK/K question cards")
        db.add(paper)
        db.flush()
    if db.query(Question).count() == 0:
        for d in QUESTIONS:
            db.add(Question(paper_id=paper.id, **d))
    db.query(Question).filter(Question.paper_id.is_(None)).update(
        {Question.paper_id: paper.id}, synchronize_session=False
    )
    for s in db.query(AssessSession).filter(AssessSession.paper_id.is_(None)).all():
        s.paper_id = paper.id
    db.commit()
