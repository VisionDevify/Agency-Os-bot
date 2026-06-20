# Telegram Live Testing

Fortuna is designed to behave like one active app screen inside Telegram.

## Testing Rule

Always target the latest active bot message.

Old visible menu boxes can remain in Telegram when Telegram refuses deletion or when a cleanup batch is still pending. Those old menus are ignored by Fortuna, and their buttons may trigger a stale-menu response instead of normal navigation.

## Reliable Flow

1. Send `/start`.
2. Wait for the fresh Home screen.
3. Prefer the newest Fortuna bot message in the chat.
4. Click buttons only inside that latest active bot message.
5. Avoid selecting the first button text match in Telegram Web, because older visible menus may contain the same labels.
6. If an old menu remains visible, treat it as historical UI and do not use it for verification.

## Stale Menu Behavior

If a stale button is tapped, Fortuna should answer:

`That menu is old. I opened a fresh Home.`

That response means stale callback protection is working.

## Browser Automation Helper Logic

Automation should:

1. Find the newest message sent by the Fortuna bot.
2. Prefer messages that include fresh Home, active screen, or current screen content.
3. Scope button searches to that newest message only.
4. Ignore older visible menu boxes unless the test is specifically validating stale callback behavior.
5. Re-run `/start` or `/clean` before broad button tests if old menu clutter is visible.

## Owner Checklist

1. Navigate through 5-10 screens.
2. Send `/start`.
3. Confirm one fresh Home appears quickly.
4. Confirm old menus disappear where Telegram permits.
5. Tap an old visible menu only if you are testing stale protection.
6. Run `/clean` if old menus remain.
7. Open Button Health and confirm Telegram UI cleanup is healthy or clearly explains what remains.
