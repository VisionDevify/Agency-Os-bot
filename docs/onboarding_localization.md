# Onboarding And Localization

Sprint 11 adds a lightweight onboarding path for pending Telegram users.

## Pending User Flow

When an unknown Telegram user sends `/start`:

1. Agency OS creates a pending user record.
2. The user selects language.
3. The user selects country.
4. The user confirms timezone.
5. The user selects 12h or 24h time format.
6. The user remains pending until Owner/Admin approval.

Pending users cannot open operational screens. They can only save profile preferences while waiting.

## Supported Languages

- English
- Spanish
- Portuguese
- Tagalog / Filipino
- Serbian

## Country And Timezone Quick Picks

- United States: `America/New_York`, `America/Chicago`, `America/Los_Angeles`
- Philippines: `Asia/Manila`
- Serbia: `Europe/Belgrade`
- Colombia: `America/Bogota`
- Brazil: `America/Sao_Paulo`
- United Kingdom: `Europe/London`

## Time Storage

- Database timestamps remain UTC.
- Local display uses the user's IANA timezone.
- Shift and quiet-hour fields are stored as local `time` values tied to the user's timezone.

## Availability Status

Availability records support:

- `on_shift`
- `off_shift`
- `away`
- `vacation`
- `unavailable`

Smart notification routing avoids direct user notification when a user is off shift, away, on vacation, unavailable, or inside quiet hours, unless a critical escalation requires it.

## Audits

Preference changes are audited with safe metadata:

- `user.language_updated`
- `user.country_updated`
- `user.timezone_updated`
- `user.time_format_updated`
- `availability.updated`
