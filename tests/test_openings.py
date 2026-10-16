"""Opening book: loads every TSV, classifies games, names continuations."""
from __future__ import annotations

import chess

from backend.openings.book import load_book


def test_book_loads_thousands_of_lines():
    book = load_book()
    assert len(book.all) > 3500
    assert len(book.by_key) > 3000


def test_italian_game_is_recognised():
    book = load_book()
    board = chess.Board()
    moves = [board.push_san(s) for s in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]]
    op, ply = book.classify_game(moves)
    assert op is not None
    assert "Italian" in op.name or "Giuoco" in op.name
    assert ply == 6


def test_leaving_book_keeps_deepest_name():
    book = load_book()
    board = chess.Board()
    sans = ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "h3", "h6", "a3", "a5"]
    moves = [board.push_san(s) for s in sans]
    op, ply = book.classify_game(moves)
    assert op is not None and "Najdorf" in op.name
    assert ply == 11  # 6.h3 is the Adams Attack; 6...h6 leaves the book


def test_search_and_continuations():
    book = load_book()
    assert any("Sicilian" in o.name for o in book.search("sicilian"))
    board = chess.Board()
    conts = book.continuations(board)
    names = {o.name for _, o in conts}
    assert "King's Pawn Game" in names or any("King's Pawn" in n for n in names)


def test_search_ranks_family_matches_first():
    hits = load_book().search("sicilian")
    assert hits[0].name == "Sicilian Defense"
    in_family = ["sicilian" in o.family.lower() for o in hits]
    assert in_family == sorted(in_family, reverse=True)  # no family match after a later-only match


def test_book_moves_follow_named_lines_through_unnamed_positions():
    book = load_book()
    board = chess.Board()
    for s in ["e4", "c5", "Nf3", "d6", "d4", "cxd4"]:
        board.push_san(s)
    conts = {board.san(mv): (op, n) for mv, op, n in book.book_moves(board)}
    # 4.Nxd4 reaches no named position, but the Najdorf, Dragon and others pass through it
    assert conts["Nxd4"][0] is None
    assert conts["Nxd4"][1] > conts["Qxd4"][1] > 0
    board.push_san("Nxd4")
    conts = {board.san(mv): n for mv, _, n in book.book_moves(board)}
    assert conts["Nf6"] > 1 and conts["g6"] > 0
