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
