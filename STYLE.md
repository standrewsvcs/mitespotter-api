# Style

How Mitespotter speaks to its users. Every user-facing string lives in
[`src/mitespotter_api/messages.toml`](./src/mitespotter_api/messages.toml);
`tests/test_messages.py` checks these rules.

## Rules

- Speak to the user: "you", present tense.
- Say what is true now. Don't narrate the system or explain what might happen.
  - Yes: "We've emailed you your recovery code."
  - No: "If an account exists for that address, an email will be sent."
- One sentence where possible. End with a full stop. Email subjects have none.
- Never reveal anything about another account: whether it exists, its address, or where an email went.
- Be plain and friendly. No exclamation marks, no jargon ("token", "session", "authenticate").
- British spelling.

## Placeholders

Email templates may use `{placeholders}`; other messages may not. A template's
placeholders are listed in its key's comment in `messages.toml`.
