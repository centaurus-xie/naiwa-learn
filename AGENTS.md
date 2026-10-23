# Repository working agreements

- Every website update must retain a visible version at the very bottom on desktop and mobile. Keep the source version in the footer and all first-party cache-busting imports consistent; bump them for frontend changes. Deployment must stamp a unique build suffix with the commit and Actions run/attempt. Do not remove or hide the version on small screens.
- Do not push to GitHub or attempt SSH authentication. The user unlocks their local SSH key and pushes. Whenever providing push instructions, include `cd /Users/yuanruitse/Documents/ust/Naiwa` first.
- Preserve unrelated user files and changes, including `preview.jpg`.
- Test card generation with mocked responses; do not read secrets or call the paid DeepSeek API just to verify a change. Preserve source grounding, one article per platform, and bounded paid retries.
