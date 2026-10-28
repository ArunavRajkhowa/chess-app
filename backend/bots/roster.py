"""The bot roster: who the player can face, how strong each one is, and how it plays. A ladder bot
rated 1400-2600 picks its moves with Maia-3 after the book (MaiaProfile); every other bot's strength is
search depth plus the selector's temperature, never the engine's Skill Level, so every line stays an
honest evaluation. scripts/calibrate_bots.py measures it into data/bot_calibration.json."""
from __future__ import annotations

from dataclasses import dataclass, field

TIER_BEGINNER = "beginner"
TIER_INTERMEDIATE = "intermediate"
TIER_ADVANCED = "advanced"
TIER_MASTER = "master"
TIER_SPECIAL = "special"
TIER_SPECIALIST = "specialist"  # generated per opening course, middlegame theme and endgame theme (specialists.py)

# Wire names for a specialist's domain; the frontend filter and the guide notes key on them.
SPECIALTY_OPENING = "opening"
SPECIALTY_MIDDLEGAME = "middlegame"
SPECIALTY_ENDGAME = "endgame"


@dataclass(frozen=True)
class SearchProfile:
    depth: int
    movetime_seconds: float | None = None
    multipv: int = 4


@dataclass(frozen=True)
class SelectionProfile:
    """temperature_cp: softmax width in centipawns (0 = always the best line).
    random_move_prob: chance of a uniformly random legal move, for the two beginners only.
    slip_prob: chance, after the book, of choosing with one enemy bishop, rook or queen out of sight (selector._blind_spot)."""
    temperature_cp: float
    random_move_prob: float = 0.0
    slip_prob: float = 0.0
    book_plies: int = 8


@dataclass(frozen=True)
class MaiaProfile:
    """elo_self: the rating Maia-3 plays as (a net plays above its label, so it is calibrated, not the label).
    temperature and top_p reshape its policy before the draw; measured in scripts/bot_humanlike.py."""
    elo_self: int
    temperature: float
    top_p: float = 1.0


@dataclass(frozen=True)
class Personality:
    """Each trait is -1..1 and nudges line scores before selection (see selector.py)."""
    aggression: float = 0.0
    solidity: float = 0.0
    trade_when_ahead: float = 0.0
    favourite_openings: tuple[str, ...] = ()
    # a book move (a favourite opening's or any named line) is played only when it costs at most
    # this much against the bot's best line at its own depth; a trap-setter accepts more
    favourite_max_loss_cp: int = 60


@dataclass(frozen=True)
class Specialty:
    """What a specialist bot trains: kind is an opening course, a middlegame theme or an endgame theme.
    start_fens: the bot's games open from one of these (engine-checked at game time) instead of move 1."""
    kind: str
    key: str
    name: str
    start_fens: tuple[str, ...] = ()


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
    specialty: Specialty | None = None
    maia: MaiaProfile | None = None  # set: Maia-3 chooses the move after the book; None: the Stockfish selector


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


def _bot(id, name, elo, tier, tagline, avatar, depth, temp, *, multipv=4, random_move=0.0, slip=0.0,
         movetime=None, personality=None, description="", maia=None, **lines) -> Bot:
    chat = {k: tuple(v) for k, v in DEFAULT_CHAT.items()}
    for k, v in PERSONALITY_CHAT.get(id, {}).items():
        chat[k] = tuple(v) + chat[k]
    return Bot(
        id=id, name=name, elo=elo, tier=tier, tagline=tagline, avatar=avatar,
        search=SearchProfile(depth=depth, movetime_seconds=movetime, multipv=multipv),
        selection=SelectionProfile(temperature_cp=temp, random_move_prob=random_move, slip_prob=slip),
        personality=personality or Personality(), description=description, chat=chat, maia=maia, **lines,
    )


# Maia's sampling, measured per lichess band on 1,000 real positions each (PLAN.md 2.2): the setting
# that keeps the top-1 human-move match within 3 points of always playing Maia's top move, with the most variety.
def _maia(elo_self: int) -> MaiaProfile:
    return MaiaProfile(elo_self, temperature=0.5, top_p=0.9)  # 1100-2200 bands: 2.3-2.8 points under argmax, runs differ 26-32%


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
    _bot("sam", "Sam", 800, TIER_BEGINNER, "Spots one-move threats", "🧢", 1, 100, multipv=5, slip=0.6,
         description="Sam sees hanging pieces and one-move captures, but misses deeper tactics."),
    # Intermediate ------------------------------------------------------------------------------
    _bot("nova", "Nova", 1000, TIER_INTERMEDIATE, "Club night regular", "✨", 2, 70, multipv=5, slip=0.55,
         description="Nova plays sensible chess and finds two-move tactics. Your first real test."),
    _bot("rafa", "Rafa", 1200, TIER_INTERMEDIATE, "Loves a gambit", "🎸", 3, 55, multipv=4, slip=0.4,
         personality=Personality(aggression=0.7, favourite_openings=("King's Gambit", "Evans Gambit", "Smith-Morra", "Scotch Gambit")),
         description="Rafa sacrifices pawns for open lines and attacks early. Keep your king safe."),
    # Maia's elo_self, 2026-10-28 (scripts/calibrate_bots.py, data/bot_calibration.json): a net plays above its
    # rating. Labels under 1400 needed an elo_self under the 600 Maia was trained on, and there the ladder broke
    # (Sam on Stockfish scored 11/18 against Nova at 450), so Pip to Rafa keep the Stockfish selector.
    # The depth and temperature stay on the Maia bots for the specialists.
    _bot("mei", "Mei", 1400, TIER_INTERMEDIATE, "Solid and patient", "🍵", 4, 55, multipv=4,
         personality=Personality(solidity=0.7, favourite_openings=("Caro-Kann", "London System", "Slav")),
         description="Mei never overextends. You will have to create something yourself.",
         maia=_maia(1100)),
    _bot("leo", "Leo", 1600, TIER_INTERMEDIATE, "Tactical and sharp", "🦁", 5, 45, multipv=4,
         personality=Personality(aggression=0.5, favourite_openings=("Sicilian", "King's Indian")),
         description="Leo calculates well in open positions. Avoid tactics you have not checked twice.",
         maia=_maia(1600)),
    # Advanced -----------------------------------------------------------------------------------
    _bot("ivy", "Ivy", 1800, TIER_ADVANCED, "Positional squeeze", "🌿", 6, 40, multipv=4,
         personality=Personality(solidity=0.5, trade_when_ahead=0.6, favourite_openings=("Queen's Gambit", "Catalan", "English")),
         description="Ivy improves her pieces, grabs space and converts small edges. Learn to make plans against her.",
         maia=_maia(1800)),
    _bot("omar", "Omar", 2000, TIER_ADVANCED, "Expert strength", "🏜️", 7, 35, multipv=4,
         description="Omar plays like a strong club expert. Few mistakes, punishes yours.",
         maia=_maia(2000)),
    _bot("zara", "Zara", 2200, TIER_ADVANCED, "Candidate master", "⚡", 9, 25, multipv=4,
         personality=Personality(aggression=0.3),
         description="Zara's attacking play is precise. Defend accurately or lose quickly.",
         maia=_maia(2200)),
    _bot("viktor", "Viktor", 2400, TIER_ADVANCED, "FIDE master", "🧊", 11, 16, multipv=3,
         personality=Personality(solidity=0.6, trade_when_ahead=0.8),
         description="Viktor grinds endgames. Expect every small advantage to be converted.",
         maia=_maia(2400)),
    # Master -------------------------------------------------------------------------------------
    _bot("elena", "Elena", 2600, TIER_MASTER, "International master", "👑", 14, 5, multipv=2,
         description="Elena plays near-perfect chess at club time controls.",
         maia=_maia(2600)),
    _bot("arjun", "Arjun", 2800, TIER_MASTER, "Grandmaster", "🐘", 16, 2, multipv=2,
         description="Grandmaster strength. Expect to learn more than you win."),
    _bot("kai", "Kai", 3000, TIER_MASTER, "Super grandmaster", "🐉", 18, 0, multipv=1, movetime=0.8,
         description="Elite strength. Study the games afterwards; the moves are the lesson."),
    _bot("stockfish", "Stockfish", 3200, TIER_MASTER, "Full engine strength", "🤖", 22, 0, multipv=1, movetime=2.0,
         description="The engine at full strength with no restraint. Nobody beats this one."),
    # Special ------------------------------------------------------------------------------------
    _bot("coach", "Coach", 1200, TIER_SPECIAL, "Adapts to you, explains moves", "🎓", 4, 60, multipv=4,
         description="Coach adapts its strength to how you are doing: harder when you are ahead, gentler when you are behind. Takebacks, threats and hints are on.",
         greeting="Let's play and learn. Ask me for a hint any time."),
    _bot("trickster", "Trickster", 1500, TIER_SPECIAL, "Sets traps every game", "🎭", 5, 45, multipv=4,
         personality=Personality(aggression=0.9, favourite_openings=("Stafford", "Englund", "Budapest", "Blackmar-Diemer", "Fried Liver", "Scholar's Mate"),
                                 favourite_max_loss_cp=150),
         description="Trickster goes for cheap tricks and opening traps. Great for learning what not to fall for."),
    _bot("wall", "The Wall", 1700, TIER_SPECIAL, "Defends everything", "🧱", 6, 35, multipv=3,
         personality=Personality(solidity=1.0, aggression=-0.6, favourite_openings=("Caro-Kann", "French", "Berlin", "Petrov")),
         description="The Wall trades pieces and keeps everything protected. Learn to break down a solid setup."),
    _bot("grinder", "The Grinder", 1900, TIER_SPECIAL, "Endgame specialist", "⚙️", 7, 26, multipv=3,
         personality=Personality(trade_when_ahead=1.0, solidity=0.4),
         description="The Grinder steers for endgames and wins them. Practice your technique."),
]

BOTS_BY_ID: dict[str, Bot] = {b.id: b for b in BOTS}


def find_bot(bot_id: str) -> Bot | None:
    """A classic bot or a generated specialist, or None."""
    from .specialists import specialist_bots  # the specialists come from content loaders: resolved on first use

    return BOTS_BY_ID.get(bot_id) or specialist_bots().get(bot_id)


def get_bot(bot_id: str) -> Bot:
    bot = find_bot(bot_id)
    if bot is None:
        raise KeyError(f"unknown bot id {bot_id!r}; known: {sorted(BOTS_BY_ID)} and the specialists")
    return bot


def bot_public(b: Bot) -> dict:
    return {
        "id": b.id, "name": b.name, "elo": b.elo, "tier": b.tier, "tagline": b.tagline,
        "avatar": b.avatar, "description": b.description, "greeting": b.greeting,
        "personality": {
            "aggression": b.personality.aggression, "solidity": b.personality.solidity,
            "trade_when_ahead": b.personality.trade_when_ahead,
            "favourite_openings": list(b.personality.favourite_openings),
        },
        "specialty": {"kind": b.specialty.kind, "key": b.specialty.key, "name": b.specialty.name} if b.specialty else None,
    }
