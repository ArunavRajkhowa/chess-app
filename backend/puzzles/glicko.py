"""Glicko-2 (Glickman 2012), the rating system lichess and chess.com use for puzzles. One rating
update per puzzle attempt: the player is rated against the puzzle and the puzzle against the player."""
from __future__ import annotations

import math
from dataclasses import dataclass

TAU = 0.5
SCALE = 173.7178
DEFAULT_RATING = 1200.0
DEFAULT_RD = 350.0
DEFAULT_VOLATILITY = 0.06


@dataclass
class Rating:
    rating: float = DEFAULT_RATING
    rd: float = DEFAULT_RD
    volatility: float = DEFAULT_VOLATILITY


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi ** 2))


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def update(player: Rating, opponent: Rating, score: float) -> Rating:
    """Returns the player's new rating after one result (1 win, 0 loss, 0.5 draw)."""
    mu = (player.rating - 1500.0) / SCALE
    phi = player.rd / SCALE
    mu_j = (opponent.rating - 1500.0) / SCALE
    phi_j = opponent.rd / SCALE
    g = _g(phi_j)
    e = _expected(mu, mu_j, phi_j)
    v = 1.0 / (g * g * e * (1.0 - e))
    delta = v * g * (score - e)

    a = math.log(player.volatility ** 2)

    def f(x: float) -> float:
        ex = math.exp(x)
        return (ex * (delta * delta - phi * phi - v - ex) / (2.0 * (phi * phi + v + ex) ** 2)) - (x - a) / (TAU * TAU)

    big_a = a
    if delta * delta > phi * phi + v:
        big_b = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        big_b = a - k * TAU
    fa, fb = f(big_a), f(big_b)
    for _ in range(100):
        if abs(big_b - big_a) <= 1e-6:
            break
        big_c = big_a + (big_a - big_b) * fa / (fb - fa)
        fc = f(big_c)
        if fc * fb <= 0:
            big_a, fa = big_b, fb
        else:
            fa /= 2.0
        big_b, fb = big_c, fc
    sigma = math.exp(big_a / 2.0)
    phi_star = math.sqrt(phi * phi + sigma * sigma)
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_new = mu + phi_new * phi_new * g * (score - e)
    return Rating(rating=mu_new * SCALE + 1500.0, rd=max(30.0, phi_new * SCALE), volatility=sigma)


def expected_score(player: Rating, opponent: Rating) -> float:
    return _expected((player.rating - 1500.0) / SCALE, (opponent.rating - 1500.0) / SCALE, opponent.rd / SCALE)
