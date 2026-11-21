"""Scoring guides shown beside each group activity on the teacher's scoring page.

Content from the teaching team's "11.15 Mock 工作台修改意见". One guide per built-in
team part (by part key); a part an admin added has no guide yet.

Each row: name ("Rating · category"), what to observe, optional score levels
[(score, description)], and example notes [(note, "2/2")].
"""

STAGE_GUIDES = {
    "Separation": {
        "cols": ("Skill", "What to observe"),
        "rows": [
            {
                "name": "SEL · Self-Management",
                "observe": "How does the child settle and join the group after saying goodbye? What support helps?",
                "examples": [
                    ("After saying goodbye, the child walked to the group and sat down independently.", "2/2"),
                    ("The child stayed by the door. After the teacher walked over and offered reassurance, "
                     "the child joined the group.", "1/2"),
                    ("The teacher offered reassurance and invited the child to sit with the group. "
                     "The child stayed by the door throughout the transition.", "0/2"),
                ],
            },
        ],
    },
    "Self Introduction": {
        "cols": ("Skill", "What to observe"),
        "rows": [
            {
                "name": "SEL · Self-Awareness",
                "observe": "Does the child express a preference, feeling, or need? Record their words or gesture "
                           "and any extra prompt.",
                "examples": [
                    ("When asked what they liked to do, the child said, “I like drawing.”", "2/2"),
                    ("The child paused. The teacher offered two choices, and the child pointed to blocks.", "1/2"),
                ],
            },
            {
                "name": "Classroom Skills · Group Participation",
                "observe": "How does the child respond when it’s their turn?",
                "examples": [
                    ("When called on, the child said their name without an extra prompt.", "2/2"),
                    ("The child introduced themselves after the teacher repeated the invitation individually.", "1/2"),
                ],
            },
            {
                "name": "Classroom Skills · Group Participation",
                "observe": "What does the child do while a peer is speaking? If reminded, what happens next?",
                "examples": [
                    ("The child waited until the peer finished before speaking.", "2/2"),
                    ("The child started talking while a peer was speaking. After a quiet reminder, "
                     "the child waited for their turn.", "1/2"),
                ],
            },
        ],
    },
    "Story Time": {
        "cols": ("Rating", "What to observe & how to score"),
        "rows": [
            {
                "name": "Follows Instructions · Classroom Skills",
                "observe": "One rating for the whole story: can the child follow the teacher's instructions or not?",
                "levels": [
                    (2, "Follows the instructions independently."),
                    (1, "Follows with assistance or an individual reminder."),
                    (0, "Cannot follow, even with assistance."),
                ],
                # shown on the Chinese page (the other rows are English only for now)
                "zh": {
                    "name": "听从指令 · 课堂技能",
                    "observe": "整个故事环节只评一次：孩子能不能跟上老师的指令？",
                    "levels": [(2, "能独立跟上指令。"), (1, "在协助或单独提醒后能跟上。"), (0, "有协助也跟不上。")],
                },
            },
            {
                "name": "Participation · Classroom Skills",
                "levels": [
                    (2, "Raises a hand independently when the group is invited to share."),
                    (1, "Raises a hand after an individual reminder."),
                    (0, "Has a clear chance to volunteer and receives a reminder, but does not raise a hand."),
                ],
                "examples": [
                    ("When the teacher invited the group to share, the child raised their hand without a reminder. "
                     "Another child was called on.", "2/2"),
                ],
            },
            {
                "name": "Focus · Classroom Skills",
                "levels": [
                    (2, "Follows the story or returns attention to it independently after a distraction."),
                    (1, "Re-engages after an individual reminder."),
                    (0, "Does not re-engage after support."),
                ],
                "examples": [
                    ("The child turned toward the hallway. After the teacher pointed back to the book, "
                     "the child turned back and followed the next page.", "1/2"),
                ],
            },
            {
                "name": "Listen to Others · Classroom Skills",
                "levels": [
                    (2, "Waits for a peer to finish speaking or responds to what the peer said."),
                    (1, "Does so after an individual reminder."),
                    (0, "Continues talking over the peer after support."),
                ],
                "examples": [
                    ("The child started speaking during a peer’s turn. After a quiet reminder, "
                     "the child waited until the peer finished.", "1/2"),
                ],
            },
            {
                "name": "Empathy · SEL / Social Awareness",
                "levels": [
                    (2, "Independently notices or responds to a character’s or peer’s feeling or need, "
                        "including after a question to the group."),
                    (1, "Does so after an extra individual cue."),
                    (0, "Has a clear opportunity and receives support, but does not show recognition "
                        "or a relevant response."),
                ],
                "examples": [
                    ("When the teacher asked the group how Pip felt, the child said, ‘He looks sad because "
                     "he lost his basket,’ without an extra cue.", "2/2"),
                ],
            },
        ],
    },
    "Cutting & Drawing": {
        "cols": ("Rating", "What to observe & how to score"),
        "rows": [
            {
                "name": "Following Directions · Classroom Skills",
                "observe": "Check three steps: ① Identifies the triangular sandwich and pastes it in the triangle "
                           "space. ② Counts the cookies and writes 2 in the box. ③ Colors the smaller square red.",
                "levels": [
                    (2, "Completes all three."),
                    (1, "Completes one or two."),
                    (0, "Completes none after having a chance to try."),
                ],
                "examples": [
                    ("The child pasted the triangular sandwich in the triangle space and colored the smaller square "
                     "red. The child said ‘two’ but left the number box blank.", "1/2"),
                ],
            },
            {
                "name": "Fine Motor Skills · Motor Observation",
                "levels": [
                    (2, "Handles the tool independently for the observed step."),
                    (1, "Completes the step with help positioning the tool or paper."),
                    (0, "Does not complete the step after receiving support."),
                ],
                "examples": [
                    ("The teacher helped position the scissors. The child then cut out the sandwich.", "1/2"),
                ],
            },
            {
                "name": "Interaction with Peers · SEL / Relationship Skills · DRDP SED 4",
                "observe": "How does the child share materials with peers?",
                "levels": [
                    (2, "Shares on their own: says “Can I use it when you’re done?” to a peer, or hands the tool "
                        "to a waiting child after using it."),
                    (1, "Sits and waits for a turn."),
                    (0, "Grabs a tool or material from another child."),
                ],
                "examples": [
                    ("A peer was waiting for the scissors. The child finished cutting and handed them over "
                     "without a reminder.", "2/2"),
                    ("The scissors were in use. The child sat and waited until they were passed over.", "1/2"),
                    ("The child pulled the scissors out of a peer’s hand.", "0/2"),
                ],
                "zh": {
                    "name": "同伴互动 · 社会情感／同伴关系 · DRDP SED 4",
                    "observe": "孩子怎么和同伴共用材料？",
                    "levels": [
                        (2, "主动分享：对同伴说 “Can I use it when you’re done?”，或用完后主动递给正在等的小朋友。"),
                        (1, "坐着等别人用完。"),
                        (0, "抢别人正在用的工具或材料。"),
                    ],
                    "examples": [
                        ("同伴在等剪刀。孩子剪完后没有提醒就主动递了过去。", "2/2"),
                        ("剪刀正在被别人用。孩子坐着等，直到剪刀被递过来。", "1/2"),
                        ("孩子从同伴手里把剪刀拽走。", "0/2"),
                    ],
                },
            },
            {
                "name": "Problem Solving · SEL · DRDP ATL 3",
                "observe": "When there are not enough materials, how does the child work it out? Most children are a 1.",
                "levels": [
                    (2, "Works out a way on their own: suggests taking turns with the scissors, or sees that the "
                        "scissors are in use and does another part first."),
                    (1, "The ordinary case: takes a material (such as the scissors), uses it and puts it back."),
                    (0, "Does not find a way, even with help."),
                ],
                "examples": [
                    ("The scissors were in use. The child colored the square first, then came back to cut "
                     "when the scissors were free.", "2/2"),
                    ("Two children wanted the glue. The child said, “You first, then me.”", "2/2"),
                    ("The child took the scissors from the middle of the table, cut, and put them back.", "1/2"),
                ],
                "zh": {
                    "name": "解决问题 · 社会情感 · DRDP ATL 3",
                    "observe": "材料不够时，孩子怎么想办法？大多数孩子是 1 分。",
                    "levels": [
                        (2, "主动想办法：提议轮流用剪刀；或发现剪刀正在被使用，就先做可以完成的另一部分。"),
                        (1, "一般情况：拿了材料（如剪刀），用完放回去。"),
                        (0, "有帮助也想不出办法。"),
                    ],
                    "examples": [
                        ("剪刀正在被别人用。孩子先给正方形涂色，等剪刀空了再回来剪。", "2/2"),
                        ("两个孩子都想用胶水。孩子说：“你先用，然后我用。”", "2/2"),
                        ("孩子从桌子中间拿了剪刀，剪完放回原处。", "1/2"),
                    ],
                },
            },
            {
                "name": "Creativity · Optional Observation",
                "levels": [
                    (2, "Adds an original detail independently during open-ended decorating time."),
                    (1, "Adds an original detail after an individual cue."),
                    (0, "Has an opportunity and receives support, but does not add an original detail."),
                ],
                "examples": [
                    ("During optional decorating time, the child drew a picnic blanket with their own pattern.", "2/2"),
                ],
            },
            {
                "name": "Persistence & Recovery · SEL / Self-Management",
                "levels": [
                    (2, "Tries again or returns to the task independently after a setback."),
                    (1, "Tries again or returns after individual encouragement or support."),
                    (0, "Has time and support, but does not try again or return during the activity."),
                ],
                "examples": [
                    ("The paper tore, and the child put down the scissors. After the teacher encouraged them "
                     "to try again, the child picked up the scissors and resumed cutting.", "1/2"),
                ],
            },
        ],
    },
}


def stage_guide(stage_key, zh=False):
    """The scoring guide for a team part, or None. zh: use a row's Chinese text where it has one."""
    g = STAGE_GUIDES.get(stage_key)
    if not g:
        return None
    rows = []
    for r in g["rows"]:
        if zh and r.get("zh"):
            r = {**r, **r["zh"]}
        title, _, tag = r["name"].partition(" · ")
        rows.append({"title": title, "tag": tag, "observe": r.get("observe", ""), "levels": r.get("levels", []),
                     "examples": r.get("examples", [])})
    return {"cols": g["cols"], "rows": rows}
