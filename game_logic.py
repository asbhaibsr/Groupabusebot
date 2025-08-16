import random
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)

TIC_TAC_TOE_GAMES = {}
TIC_TAC_TOE_TASK = {}

WINNING_COMBINATIONS = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],
    [0, 3, 6], [1, 4, 7], [2, 5, 8],
    [0, 4, 8], [2, 4, 6]
]

async def end_tictactoe_game(client, chat_id: int):
    if chat_id in TIC_TAC_TOE_GAMES:
        game = TIC_TAC_TOE_GAMES.pop(chat_id)
        if game.get("message_id"):
            try:
                await client.edit_message_text(
                    chat_id=chat_id,
                    message_id=game['message_id'],
                    text="😔 <b>Game has been cancelled due to inactivity.</b>",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                )
            except Exception as e:
                logger.error(f"Failed to edit game message on timeout: {e}")
    if chat_id in TIC_TAC_TOE_TASK:
        task = TIC_TAC_TOE_TASK.pop(chat_id)
        task.cancel()

def check_win(board):
    for combo in WINNING_COMBINATIONS:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] and board[combo[0]] != "➖":
            return board[combo[0]]
    return None

def check_draw(board):
    return all(cell != "➖" for cell in board)

def get_tictac_keyboard(board, end_game=False):
    keyboard = []
    for i in range(3):
        row = []
        for j in range(3):
            index = i * 3 + j
            row.append(InlineKeyboardButton(board[index], callback_data=f"tictac_{index}" if not end_game else "tictac_noop"))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)
