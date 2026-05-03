"""
core/youtube_metadata_engine.py — YouTube Shorts Metadata Engine.

Generates YouTube-ready title, description, and tags from a raw Instagram caption.

Pipeline:
  1. Clean    — strip hashtags, normalize whitespace
  2. Classify — keyword scoring → Islamic content category
  3. Build    —
       Title       : punchy hook + "| Islamic Reminder #Shorts" (max 100 chars)
       Description : PRE-HOOK + BODY + EMOTIONAL LINE + HASHTAGS + CREDIT
       Tags        : YouTube-optimized tag list for the detected category

Categories: sabr | shukr | tawakkul | akhirah | dua | general

Usage:
    from core.youtube_metadata_engine import build_metadata
    meta = build_metadata(original_caption="...", credit_handle="softeningsayings")
    # meta = {"title": str, "description": str, "tags": list[str], "category": str}
"""

import re
import random

# ── Category keyword banks ─────────────────────────────────────────────────────
_KEYWORDS: dict[str, list[str]] = {
    "sabr":     ["pain","struggle","test","patience","hardship","trial","difficult","burden","suffering","sabr","endure","ease after","darkness","wound","broken","heartbreak","hurt"],
    "shukr":    ["gratitude","blessing","rizq","thankful","grateful","alhamdulillah","bounty","favour","mercy","provision","gift","appreciate","shukr","contentment","satisfied"],
    "tawakkul": ["trust","control","plan","rely","depend","tawakkul","allah's plan","let go","worry","outcome","overthink","surrender","put your trust","leave it to allah"],
    "akhirah":  ["death","jannah","grave","hereafter","paradise","akhirah","afterlife","eternal","day of judgement","qiyamah","duniya","dunya","temporary","accountability"],
    "dua":      ["pray","dua","forgive","supplication","ask allah","make dua","du'a","prayer","supplicate","raise your hands","3am","night prayer","ameen","ya allah","forgiveness"],
}

# ── Title hooks ────────────────────────────────────────────────────────────────
_TITLE_HOOKS: dict[str, list[str]] = {
    "sabr":     ["When Allah Tests You 🤲","Hold On — Allah Sees Your Pain 🌙","Every Hardship Has a Purpose 🤍","Sabr — The Secret of the Believer ✨","You Are Not Alone in This Test 🌙"],
    "shukr":    ["Count Your Blessings — Alhamdulillah 🤍","Allah's Blessings Are Endless ✨","Gratitude Changes Everything 🌙","Say Alhamdulillah Right Now 🤲","Your Rizq Is Already Written 🌙"],
    "tawakkul": ["Trust Allah's Plan — Always 🌙","Let Go and Trust Allah 🤍","Stop Worrying — Allah Is in Control ✨","Tawakkul: The Believer's Superpower 🤲","Leave It to Allah 🌙"],
    "akhirah":  ["This World Is Temporary — Remember 🕌","Are You Ready for What Comes Next? 🌙","Jannah Is the Goal 🤍","What Are You Building for the Akhirah? ✨","The Grave Is Closer Than You Think 🌙"],
    "dua":      ["Make Du'a — Allah Always Listens 🤲","Your Du'a Reaches Allah at 3AM 🌙","Never Stop Making Du'a 🤍","Call Upon Allah — He Will Respond ✨","The Power of a Sincere Du'a 🤲"],
    "general":  ["A Reminder Every Muslim Needs 🤍","SubhanAllah — Read This Twice 🌙","This Will Touch Your Heart ✨","A Reminder for Your Soul Today 🤍","May Allah Bless You — SubhanAllah 🌙"],
}

# ── Description pre-hooks (first visible line) ────────────────────────────────
_PRE_HOOKS: dict[str, list[str]] = {
    "sabr":     ["💬 Comment 'Ameen' if you needed this today 🤲","💬 Type 'Ameen' if you're going through a test right now 🌙","💬 Comment 'Ameen' — this is for the ones still holding on 🤍"],
    "shukr":    ["💬 Comment 'Alhamdulillah' if you're grateful today 🤍","💬 Type 'Alhamdulillah' — let's fill the comments with gratitude ✨","💬 Say 'Alhamdulillah' if you woke up with more than you deserve 🌙"],
    "tawakkul": ["💬 Comment 'Ameen' if you're trusting Allah's plan today 🌙","💬 Type 'Ameen' if you're learning to let go and trust Allah 🤍","💬 Say 'Ameen' if you're leaving it all to Allah today ✨"],
    "akhirah":  ["💬 Share this before scrolling — someone needs to see this 🕌","💬 Comment 'Ameen' if you're preparing for what truly matters 🌙","💬 Tag someone who needs this reminder today 🤍"],
    "dua":      ["💬 Comment 'Ameen' and make a du'a right now 🤲","💬 Type 'Ameen' — let's all raise our hands together 🌙","💬 Comment your du'a below — Allah is always listening 🤍"],
    "general":  ["💬 Comment 'Ameen' if this speaks to you today 🤍","💬 Type 'SubhanAllah' if this touched your heart ✨","💬 Comment 'Ameen' — share this with someone who needs it 🌙"],
}

# ── Emotional lines (Quranic / Hadith references) ─────────────────────────────
_EMOTIONAL_LINES: dict[str, list[str]] = {
    "sabr":     ["«لَا يُكَلِّفُ اللَّهُ نَفْسًا إِلَّا وُسْعَهَا» — Allah does not burden a soul beyond what it can bear. (2:286)","«إِنَّ مَعَ الْعُسْرِ يُسْرًا» — Indeed, with every hardship comes ease. (94:6)","Your sabr is not wasted — Allah sees every tear, every silent prayer."],
    "shukr":    ["«لَئِن شَكَرْتُمْ لَأَزِيدَنَّكُمْ» — If you are grateful, I will surely increase you. (14:7)","«وَإِن تَعُدُّوا نِعْمَةَ اللَّهِ لَا تُحْصُوهَا» — You cannot count Allah's blessings. (16:18)","The believer who is grateful is always in a state of increase."],
    "tawakkul": ["«وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ» — Whoever relies upon Allah, He is sufficient. (65:3)","Allah's timing is always perfect — even when it doesn't feel like it.","Tawakkul is doing your best, then leaving the rest to Allah completely."],
    "akhirah":  ["«كُلُّ نَفْسٍ ذَائِقَةُ الْمَوْتِ» — Every soul shall taste death. (3:185) Prepare while you can.","What you plant in this dunya, you will harvest in the akhirah.","This life is a bridge — don't build your home on it."],
    "dua":      ["«ادْعُونِي أَسْتَجِبْ لَكُمْ» — Call upon Me, I will respond to you. (40:60)","«وَإِذَا سَأَلَكَ عِبَادِي عَنِّي فَإِنِّي قَرِيبٌ» — I am near. (2:186) Always.","A believer's most powerful weapon is du'a — never leave it."],
    "general":  ["May Allah fill your heart with peace — «السَّلَامُ» is one of His beautiful names.","Return to Allah — He is always waiting for you, no matter how far you've gone.","Every moment is a chance to start again. That is the mercy of Allah."],
}

# ── YouTube description hashtags ──────────────────────────────────────────────
_HASHTAGS: dict[str, str] = {
    "sabr":     "#Sabr #Patience #Islam #Muslim #IslamicReminder #Quran #Allah #Alhamdulillah #Hardship #Tawakkul #SubhanAllah #IslamicShorts #IslamicQuotes #ImanBooster #Shorts",
    "shukr":    "#Shukr #Alhamdulillah #Gratitude #Rizq #Islam #Muslim #Quran #Allah #Barakah #IslamicShorts #IslamicReminder #IslamicQuotes #SubhanAllah #Tawakkul #Shorts",
    "tawakkul": "#Tawakkul #Trust #AllahsPlan #Islam #Muslim #Quran #Allah #SubhanAllah #Iman #IslamicShorts #IslamicReminder #IslamicQuotes #Faith #Sabr #Deen #Shorts",
    "akhirah":  "#Akhirah #Jannah #Islam #Muslim #Quran #Allah #IslamicReminder #Hereafter #Deen #IslamicShorts #IslamicQuotes #SubhanAllah #Salah #Iman #LastDay #Shorts",
    "dua":      "#Dua #Prayer #Islam #Muslim #Quran #Allah #MakeDua #IslamicReminder #IslamicShorts #Dhikr #SubhanAllah #Alhamdulillah #AllahuAkbar #Ameen #Iman #Shorts",
    "general":  "#Islam #Islamic #Quran #Allah #Muslim #Hadith #ProphetMuhammad #IslamicQuotes #Iman #Tawakkul #Sabr #Dhikr #Jannah #Deen #IslamicReminder #IslamicShorts #SubhanAllah #AllahuAkbar #Alhamdulillah #Shorts",
}

# ── YouTube video tags ─────────────────────────────────────────────────────────
_TAGS: dict[str, list[str]] = {
    "sabr":     ["Islamic Reminder","Sabr","Patience in Islam","Muslim Motivation","Quran","Allah","Islamic Shorts","Hadith","Muslim","Islam","SubhanAllah","Tawakkul","Iman","Deen","Islamic Quotes","#Shorts"],
    "shukr":    ["Islamic Reminder","Shukr","Alhamdulillah","Gratitude in Islam","Muslim Motivation","Quran","Allah","Islamic Shorts","Rizq","Muslim","Islam","Blessing","Islamic Quotes","Hadith","SubhanAllah","#Shorts"],
    "tawakkul": ["Islamic Reminder","Tawakkul","Trust Allah","Allah's Plan","Muslim Motivation","Quran","Allah","Islamic Shorts","Muslim","Islam","SubhanAllah","Iman","Deen","Islamic Quotes","Hadith","Sabr","#Shorts"],
    "akhirah":  ["Islamic Reminder","Akhirah","Jannah","Hereafter","Death in Islam","Muslim Motivation","Quran","Allah","Islamic Shorts","Muslim","Islam","SubhanAllah","Iman","Islamic Quotes","Hadith","Day of Judgement","#Shorts"],
    "dua":      ["Islamic Reminder","Dua","Prayer in Islam","Muslim Motivation","Quran","Allah","Islamic Shorts","Dhikr","Muslim","Islam","SubhanAllah","Ameen","Iman","Deen","Islamic Quotes","Hadith","Supplication","#Shorts"],
    "general":  ["Islamic Reminder","Muslim Motivation","Quran","Allah","Islamic Shorts","Hadith","Prophet Muhammad","Muslim","Islam","SubhanAllah","Alhamdulillah","AllahuAkbar","Iman","Deen","Islamic Quotes","Tawakkul","Sabr","Jannah","#Shorts"],
}


# ── Public API ────────────────────────────────────────────────────────────────

def clean_caption(text: str) -> str:
    """Strip hashtags and normalize whitespace. Keeps emojis and Arabic text."""
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(l.rstrip() for l in text.splitlines()).strip()


def classify_caption(text: str) -> str:
    """Return the highest-scoring category for the caption, or 'general'."""
    lower = text.lower()
    scores = {cat: sum(1 for kw in kws if kw in lower) for cat, kws in _KEYWORDS.items()}
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else "general"


def build_metadata(
    original: str,
    add_credit: bool = True,
    credit_handle: str = "softeningsayings",
) -> dict:
    """
    Full pipeline — returns a dict with YouTube-ready title, description, and tags.

    Returns:
        {
            "title":       str,        # max 100 chars, ends with #Shorts
            "description": str,        # full YouTube description
            "tags":        list[str],  # YouTube video tags
            "category":    str,        # detected Islamic category (for logging)
        }
    """
    body     = clean_caption(original)
    category = classify_caption(body)

    title_hook = random.choice(_TITLE_HOOKS[category])
    pre_hook   = random.choice(_PRE_HOOKS[category])
    emotional  = random.choice(_EMOTIONAL_LINES[category])

    # Title — #Shorts in title is critical for YouTube to classify the video as a Short.
    # We calculate the suffix first so [:100] can never silently chop it off.
    _SHORTS_SUFFIX = " | Islamic Reminder #Shorts"
    max_hook = 100 - len(_SHORTS_SUFFIX)
    title = title_hook[:max_hook] + _SHORTS_SUFFIX

    # Description
    desc_parts = [pre_hook, "", body, "", emotional, "", _HASHTAGS[category]]
    if add_credit:
        desc_parts += ["", f"Via @{credit_handle} 🤍"]

    return {
        "title":       title,
        "description": "\n".join(desc_parts),
        "tags":        _TAGS[category],
        "category":    category,
    }
