# JARVIS Reflexes and Actions

This document lists the currently implemented "reflexes" (fast, rule-based triggers) and the supported intents that the AI planner can use.

## 1. Fast Reflexes (Instant Recognition)
These commands bypass the LLM for near-instant execution.

### Browser Navigation
- **Open App**: "Open [app]", "Go to [website]", "Launch [app]"
- **Search**: "Search for [query]", "Find [query] on [app]", "Open [app] and search for [query]"
- **Navigation**: "Go back", "Back", "Go forward", "Forward", "Reload", "Refresh"
- **Tabs**: "New tab", "Close tab", "Reopen tab", "Duplicate tab", "Next tab", "Previous tab"
- **Browser Utilities**: "Address bar", "Copy URL", "History", "Bookmarks", "Downloads", "Incognito", "Console", "Inspect", "Zoom in/out/reset"

### Browser Interaction
- **Ordinal Clicking**: "Click the first/second/.../last [element]" (e.g., "Click the second video")
- **Direct Clicking**: "Click [button name]", "Press [key]" (Enter, Escape, Tab)
- **Page Movement**: "Scroll down", "Scroll up", "Page down", "Page up", "Top of page", "Bottom of page"

### PC / System Actions
- **File Management**: "Open [folder] folder", "Find [file] file"
- **Known Folders**: "Open desktop/downloads/documents/pictures/videos/music"
- **Windows**: "Minimize window", "Maximize window", "Snap left", "Snap right", "Switch window", "Close window", "Lock PC"
- **Apps**: "Open notepad/calculator/paint/terminal/PowerShell/VS Code/Brave/Edge/Discord/Spotify/Slack/WhatsApp/Telegram/Teams/Zoom/Steam"
- **Media**: "Play/Pause", "Next track", "Previous track", "Volume up/down", "Mute", "Fullscreen"
- **Dictation**: "Type this: [text]", "Dictate: [text]"
- **Editing**: "Copy", "Paste", "Undo", "Redo", "Select all", "Save", "Bold", "Italic", "Find on page"
- **System Info**: "What time is it?", "Today's date", "Check battery", "System health"

Not every useful command should be a reflex. Fragile actions like pinning/muting a browser tab or shutdown/restart stay out of the instant layer until they have a reliable implementation and a confirmation policy.

### Chat / Writing
- **Grammar/Reply**: "Correct this: [text]", "Reply to this: [text]"
- **Greetings**: "Hello", "How are you?", "Who are you?"

---

## 2. AI Actions (Planner Intents)
When a command doesn't match a reflex, the LLM plans using these intents:

| Intent | Description |
| :--- | :--- |
| `open_app` | Navigates the browser to a specific application or URL. |
| `browser_action` | Generic browser tasks (clicking, typing, finding info). |
| `send_message` | Drafts or sends messages (WhatsApp, Gmail). |
| `summarize` | Summarizes the current page or email thread. |
| `reply_professionally` | Generates a professional reply to an email. |
| `create_task` | Creates a task in Notion or similar apps. |
| `pc_action` | System-level tasks (launching apps, window management). |
| `chat` | General conversation and assistance. |
| `unknown` | Triggered when the command is not understood. |

---

## 3. Learning & Teaching
- **Teach Mode**: "Teach me [command]" or "Teach JARVIS [command]"
- **Save Agent**: "Save this agent as [name]"
- **Load Agent**: "Switch to [name] agent"
