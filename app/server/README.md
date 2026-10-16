# app/server/ (Dev2)

App server + SQLite knowledge store. See `app/server/CLAUDE.md` for the rules and `docs/MVP_Master_Plan.md` §2.9 for the features (I1–I8).

## SSE events (internal to the App track)

| Event | Payload | Sent when |
|---|---|---|
| `case.ended` | `case_id` | Replay reaches the end of the video |
| `answer.confirmed` | `question_id`, `record_id` | Surgeon taps Confirm |
| `record.created` | DecisionRecord | Record stored |
| `graph.updated` | changed node and edge IDs | Graph changes |

## Usage

To be written as features land.
