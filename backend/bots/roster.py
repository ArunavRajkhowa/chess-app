"""The bot roster: who the player can face, how strong each one is, and how it plays. A bot's
strength comes from search depth plus the selector's temperature (backend/bots/selector.py), not
from the engine's own Skill Level, so every bot's lines are honest evaluations."""
from __future__ import annotations

from dataclasses import dataclass, field

TIER_BEGINNER = "beginner"
TIER_INTERMEDIATE = "intermediate"
TIER_ADVANCED = "advanced"
TIER_MASTER = "master"
TIER_SPECIAL = "special"


@dataclass(frozen=True)
class SearchProfile:
    depth: int
    movetime_seconds: float | None = None
    multipv: int = 4


@dataclass(frozen=True)
class SelectionProfile:
    """temperature_cp: softmax width in centipawns (0 = always the best line).
    random_move_prob: chance of a uniformly random legal move, for the weakest bots only."""
    temperature_cp: float
    random_move_prob: float = 0.0
    book_plies: int = 8


@dataclass(frozen=True)
class Personality:
    """Each trait is -1..1 and nudges line scores before selection (see selector.py)."""
    aggression: float = 0.0
    solidity: float = 0.0
    trade_when_ahead: float = 0.0
    favourite_openings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Bot:
    id: str
    name: str
    elo: int
    tier: str
    tagline: str
    avatar: str  # emoji or a key the frontend maps to an illustration
    search: SearchProfile
    selection: SelectionProfile
    personality: Personality = field(default_factory=Personality)
    greeting: str = "Good luck, have fun!"
    on_win: str = "Good game! Review it to see what we can learn."
    on_loss: str = "Well played! You got me this time."
    on_draw: str = "A draw. Fair result."
    description: str = ""
    chat: dict[str, tuple[str, ...]] = field(default_factory=dict)


# What a bot says when something happens. Keys are events the play API detects after each move pair.
CHAT_EVENTS = ("capture_mine", "capture_yours", "check_given", "check_received", "long_game", "bot_winning", "bot_losing")
DEFAULT_CHAT: dict[str, tuple[str, ...]] = {
    "capture_mine": ("Ouch. I needed that one.", "Fair capture. I will get it back.", "Hmm. I did not see that."),
    "capture_yours": ("Thank you for the piece.", "I will take that.", "One for me."),
    "check_given": ("Check.", "Your king looks lonely.", "Careful now."),
    "check_received": ("A check. Noted.", "I see your check. My king is fine.", "Checks are cheap; mates are not."),
    "long_game": ("A long fight. I like those.", "Still here. Are you?"),
    "bot_winning": ("The material is on my side now.", "This is going well for me. Find something."),
    "bot_losing": ("You are ahead. Do not relax.", "I am worse. Let us see if you can convert."),
}
PERSONALITY_CHAT: dict[str, dict[str, tuple[str, ...]]] = {
    "pip": {"capture_mine": ("Oh no, my piece!", "Wait, you can do that?"), "capture_yours": ("I took something! Is that good?",), "check_given": ("Is this check? I think it is check!",), "bot_losing": ("I am losing again, aren't I?",)},
    "max": {"capture_yours": ("Mine! All mine!", "Grab first, think later."), "capture_mine": ("Hey! Give that back.",), "check_given": ("Run, king, run!",)},
    "rafa": {"capture_mine": ("A pawn for the initiative. Worth it.",), "check_given": ("The attack begins.",), "bot_losing": ("Material is temporary. Pressure is forever.",)},
    "mei": {"capture_mine": ("Patience. Everything is still protected.",), "bot_winning": ("Small advantages, one at a time.",)},
    "trickster": {"capture_yours": ("Did you see the trap? There is another one.",), "check_given": ("Surprise.",), "bot_losing": ("Fine. No more tricks. Maybe.",)},
    "wall": {"capture_mine": ("Even walls lose a brick now and then.",), "check_received": ("You will need more than a check.",)},
    "grinder": {"bot_winning": ("Now we grind.",), "long_game": ("The endgame is where I live.",)},
    "coach": {"capture_mine": ("Good. You saw the loose piece.",), "capture_yours": ("That was hanging. Check what my pieces attack before you move.",), "check_received": ("Nice check. Did it gain anything?",), "bot_losing": ("You are winning. Simplify: trade pieces, not pawns.",)},
    "stockfish": {"capture_mine": ("Noted.",), "capture_yours": ("Correct.",), "check_given": ("Check.",)},
}


def _bot(id, name, elo, tier, tagline, avatar, depth, temp, *, multipv=4, random_move=0.0,
         movetime=None, personality=None, description="", **lines) -> Bot:
    chat = {k: tuple(v) for k, v in DEFAULT_CHAT.items()}
    for k, v in PERSONALITY_CHAT.get(id, {}).items():
        chat[k] = tuple(v) + chat[k]
    return Bot(
        id=id, name=name, elo=elo, tier=tier, tagline=tagline, avatar=avatar,
        search=SearchProfile(depth=depth, movetime_seconds=movetime, multipv=multipv),
        selection=SelectionProfile(temperature_cp=temp, random_move_prob=random_move),
        personality=personality or Personality(), description=description, chat=chat, **lines,
    )


BOTS: list[Bot] = [
    # Beginner -----------------------------------------------------------------------------------
    _bot("pip", "Pip", 250, TIER_BEGINNER, "Just learned the rules", "🐣", 1, 400, multipv=10, random_move=0.35,
         description="Pip hangs pieces, forgets about checks and loves pushing pawns. Perfect for a first game.",
         greeting="Hi! I only learned chess last week. Be gentle!"),
    _bot("max", "Max", 400, TIER_BEGINNER, "Grabs every piece in sight", "🦊", 1, 250, multipv=8, random_move=0.2,
         personality=Personality(aggression=0.8),
         description="Max takes anything he can and chases your queen. Punish greedy captures.",
         greeting="Let's go! I like taking pieces."),
    _bot("luna", "Luna", 600, TIER_BEGINNER, "Knows the opening principles", "🌙", 2, 150, multipv=6, random_move=0.08,
         description="Luna develops her pieces and castles, then drifts. Good practice for simple tactics."),
    _bot("sam", "Sam", 800, TIER_BEGINNER, "Spots one-move threats", "🧢", 3, 100, multipv=5, random_move=0.03,
         description="Sam sees hanging pieces and one-move captures, but misses deeper tactics."),
    # Intermediate ------------------------------------------------------------------------------
    _bot("nova", "Nova", 1000, TIER_INTERMEDIATE, "Club night regular", "✨", 4, 70, multipv=4,
         description="Nova plays sensible chess and finds two-move tactics. Your first real test."),
    _bot("rafa", "Rafa", 1200, TIER_INTERMEDIATE, "Loves a gambit", "🎸", 5, 50, multipv=4,
         personality=Personality(aggression=0.7, favourite_openings=("King's Gambit", "Evans Gambit", "Smith-Morra", "Scotch Gambit")),
         description="Rafa sacrifices pawns for open lines and attacks early. Keep your king safe."),
    _bot("mei", "Mei", 1400, TIER_INTERMEDIATE, "Solid and patient", "🍵", 6, 35, multipv=3,
         personality=Personality(solidity=0.7, favourite_openings=("Caro-Kann", "London System", "Slav")),
         description="Mei never overextends. You will have to create something yourself."),
    _bot("leo", "Leo", 1600, TIER_INTERMEDIATE, "Tactical and sharp", "🦁", 8, 25, multipv=3,
         personality=Personality(aggression=0.5, favourite_openings=("Sicilian", "King's Indian")),
         description="Leo calculates well in open positions. Avoid tactics you have not checked twice."),
    # Advanced -----------------------------------------------------------------------------------
    _bot("ivy", "Ivy", 1800, TIER_ADVANCED, "Positional squeeze", "🌿", 10, 15, multipv=2,
         personality=Personality(solidity=0.5, trade_when_ahead=0.6, favourite_openings=("Queen's Gambit", "Catalan", "English")),
         description="Ivy improves her pieces, grabs space and converts small edges. Learn to make plans against her."),
    _bot("omar", "Omar", 2000, TIER_ADVANCED, "Expert strength", "🏜️", 12, 10, multipv=2,
         description="Omar plays like a strong club expert. Few mistakes, punishes yours."),
    _bot("zara", "Zara", 2200, TIER_ADVANCED, "Candidate master", "⚡", 14, 6, multipv=2,
         personality=Personality(aggression=0.3),
         description="Zara's attacking play is precise. Defend accurately or lose quickly."),
    _bot("viktor", "Viktor", 2400, TIER_ADVANCED, "FIDE master", "🧊", 16, 4, multipv=2,
         personality=Personality(solidity=0.6, trade_when_ahead=0.8),
         description="Viktor grinds endgames. Expect every small advantage to be converted."),
    # Master -------------------------------------------------------------------------------------
    _bot("elena", "Elena", 2600, TIER_MASTER, "International master", "👑", 18, 2, multipv=2,
         description="Elena plays near-perfect chess at club time controls."),
    _bot("arjun", "Arjun", 2800, TIER_MASTER, "Grandmaster", "🐘", 20, 1, multipv=2, movetime=0.8,
         description="Grandmaster strength. Expect to learn more than you win."),
    _bot("kai", "Kai", 3000, TIER_MASTER, "Super grandmaster", "🐉", 22, 0, multipv=1, movetime=1.5,
         description="Elite strength. Study the games afterwards; the moves are the lesson."),
    _bot("stockfish", "Stockfish", 3200, TIER_MASTER, "Full engine strength", "🤖", 24, 0, multipv=1, movetime=2.5,
         description="The engine at full strength with no restraint. Nobody beats this one."),
    # Special ------------------------------------------------------------------------------------
    _bot("coach", "Coach", 1200, TIER_SPECIAL, "Adapts to you, explains moves", "🎓", 6, 40, multipv=4,
         description="Coach adapts its strength to how you are doing: harder when you are ahead, gentler when you are behind. Takebacks, threats and hints are on.",
         greeting="Let's play and learn. Ask me for a hint any time."),
    _bot("trickster", "Trickster", 1500, TIER_SPECIAL, "Sets traps every game", "🎭", 7, 30, multipv=4,
         personality=Personality(aggression=0.9, favourite_openings=("Stafford", "Englund", "Budapest", "Blackmar-Diemer", "Fried Liver", "Scholar's Mate")),
         description="Trickster goes for cheap tricks and opening traps. Great for learning what not to fall for."),
    _bot("wall", "The Wall", 1700, TIER_SPECIAL, "Defends everything", "🧱", 9, 20, multipv=3,
         personality=Personality(solidity=1.0, aggression=-0.6, favourite_openings=("Caro-Kann", "French", "Berlin", "Petrov")),
         description="The Wall trades pieces and keeps everything protected. Learn to break down a solid setup."),
    _bot("grinder", "The Grinder", 1900, TIER_SPECIAL, "Endgame specialist", "⚙️", 11, 12, multipv=2,
         personality=Personality(trade_when_ahead=1.0, solidity=0.4),
         description="The Grinder steers for endgames and wins them. Practice your technique."),
]

BOTS_BY_ID: dict[str, Bot] = {b.id: b for b in BOTS}


def get_bot(bot_id: str) -> Bot:
    try:
        return BOTS_BY_ID[bot_id]
    except KeyError:
        raise KeyError(f"unknown bot id {bot_id!r}; known: {sorted(BOTS_BY_ID)}")


def bot_public(b: Bot) -> dict:
    return {
        "id": b.id, "name": b.name, "elo": b.elo, "tier": b.tier, "tagline": b.tagline,
        "avatar": b.avatar, "description": b.description, "greeting": b.greeting,
        "personality": {
            "aggression": b.personality.aggression, "solidity": b.personality.solidity,
            "trade_when_ahead": b.personality.trade_when_ahead,
            "favourite_openings": list(b.personality.favourite_openings),
        },
    }
