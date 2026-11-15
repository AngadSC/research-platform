"""Emoji reactions on chat messages (D321), shared by project and lab chat.

A message stores its reactions as `{emoji: [user id, ...]}` in a JSON field: a handful per
message, read with the message itself, so no second query and no extra table to scope. Whoever
can read a chat can react in it, as whoever can read it can post (D206).
"""

import unicodedata

from django.db import transaction
from rest_framework.exceptions import ValidationError

MAX_EMOJI_CHARS = 16  # one emoji with skin tone and joiners fits; a sentence does not
MAX_KINDS = 20  # different emoji on one message


def _joiner(ch) -> bool:
    return ch == "\u200d" or 0xE0020 <= ord(ch) <= 0xE007F


def clean_emoji(value) -> str:
    """One emoji, or ValidationError. No ASCII at all (so no text, markup or digits), no spaces
    or control characters, and at least one symbol."""
    s = str(value or "")
    if not s or len(s) > MAX_EMOJI_CHARS or any(c.isascii() for c in s):
        raise ValidationError({"emoji": ["Pick an emoji."]})
    cats = [unicodedata.category(c) for c in s]
    # Of the format characters only the joiner and emoji tag characters: never bidi overrides.
    if any(cat[0] in "CZ" and not _joiner(ch) for ch, cat in zip(s, cats, strict=True)):
        raise ValidationError({"emoji": ["Pick an emoji."]})
    if "So" not in cats:
        raise ValidationError({"emoji": ["Pick an emoji."]})
    return s


def toggle(queryset, pk, user, emoji):
    """Add `user`'s `emoji` to the message, or take it away if it is there. Under a row lock, so
    two people reacting at once both count. Returns the message."""
    emoji = clean_emoji(emoji)
    uid = str(user.pk)
    with transaction.atomic():
        message = queryset.select_for_update(of=("self",)).get(pk=pk)
        reactions = {k: list(v) for k, v in (message.reactions or {}).items()}
        people = reactions.get(emoji, [])
        if uid in people:
            people.remove(uid)
        else:
            if emoji not in reactions and len(reactions) >= MAX_KINDS:
                raise ValidationError(
                    {"emoji": ["This message has all the reactions it can take."]}
                )
            people.append(uid)
        if people:
            reactions[emoji] = people
        else:
            reactions.pop(emoji, None)
        message.reactions = reactions
        message.save(update_fields=["reactions", "updated_at"])
    return message


def summary(reactions, user) -> list[dict]:
    """What a reader sees: each emoji, how many, and whether they are one of them. In the order
    the emoji were first used."""
    uid = str(getattr(user, "pk", ""))
    return [
        {"emoji": emoji, "count": len(people), "mine": uid in people}
        for emoji, people in (reactions or {}).items()
        if people
    ]
