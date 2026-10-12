# Website changelog

This records changes to the independent tax and visa assistant. The submitted report is separate from this website.

## Pending review — 12 October 2026

- Matched three common phrasings to government-source notes already in the index: HELP loan withholding, working-from-home expenses, and checking whether a held visa is still valid in VEVO. These routes work even when the other topic is selected in the browser.
- Routed “taxes” to the tax topic, so a question about paying taxes no longer points to Home Affairs when the visa topic happens to be selected. The assistant still avoids inventing payment steps it has not indexed.
- Stopped a general “change my course” question from retrieving provider-transfer rules that may concern a different situation.
- Made the no-source response clearer for a genuine question. Personal HELP withholding, home-office deduction and visa-expiry questions now show the reviewed source extract and official link instead of asking the model to decide an individual's case.
- Added regression checks for these cases. **44 backend tests pass.** No new source pages or notes were added in this round.

The website code changes in this section are available in the local working copy for review. Publishing this changelog does not publish that code. The Cloudflare tunnel remains off.

## Previously completed — 12 October 2026

- Replaced the misleading “no matching source note” response to nonsense such as `aaaaa` with a request for a complete question, without an unrelated official link.
- Added optional local semantic matching for clear paraphrases that keyword search misses. The existing source and confidence checks still apply, and keyword search remains available when the embedding model is off.
- Expanded the index to 71 technically active notes from 55 distinct official pages, with broader search across approved notes.
