# JARVIS Command Guide

JARVIS is fastest when you speak in short operator-style commands. The runtime tries actions in this order:

```text
reflex -> remembered site action -> semantic DOM action -> local LLM decision
```

Use the visible browser for normal control:

```env
USE_OBSCURA=false
BROWSER_EXECUTABLE_PATH=C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe
```

Use Obscura only for headless scraping, stealth/background jobs, or pages where you do not need to see the browser.

## Browser Reflexes

```text
open youtube
open github and search voice assistant
search latest ai news
search headphones on amazon
click sign in
click first video
open second result
click last link
new tab
close tab
reload
go back
go forward
copy current url
find on page pricing
fullscreen
```

## PC Reflexes

```text
launch brave
launch vs code
launch notepad
launch terminal
type hello world
press enter
copy selected text
copy hello world
paste
paste hello world
take screenshot
switch window
close window
minimize window
maximize window
snap window left
snap window right
open desktop
open downloads
open documents
find file invoice
open folder games
rename this to final report
delete temp file
kill notepad
```

Guarded commands such as `delete`, `kill`, `rename`, sending messages, checkout/payment, login, credentials, and account changes require confirmation. Shell/install commands are refused in safe mode.

## Messaging & Chat Reflexes

JARVIS has two ways to handle messaging. For complex apps like Gmail or WhatsApp, it can navigate and draft. For quick "reflex" typing in any focused app, it uses an LLM to polish your words instantly.

### Smart Chat Reflexes (LLM-Powered)
These phrases trigger a one-shot LLM call to draft or correct text, then type it into your active window instantly.

```text
write this back: [instruction/reply]
reply: [reply text]
draft a message: [instruction]
grammar correct: [sloppy text]
correct this: [text to fix]
```

### Direct Dictation (High-Speed Voice-to-Text)
If you want raw transcription without any AI "thinking", use these. JARVIS will type exactly what you say, immediately.

```text
type this: [text]
write: [text]
dictate: [text]
just type: [text]
```

### Heavyweight Messaging (App-Specific)
For complex multi-step drafting in specific browser apps:

```text
draft a message to Alex saying I will be late
send whatsapp to Alex saying on my way
draft an email to Sarah saying the report is ready
```

`draft` never sends. `send` asks for confirmation before it sends.

## How JARVIS Improves

JARVIS records successful UI actions per site. For example, if clicking a YouTube video works once, it can remember the selector for that domain and try it before asking the LLM next time.

It can also learn a whole browser workflow from you:

```text
teach me upload the daily report
```

Or, if a browser task fails, JARVIS asks whether you want to teach it. Say yes, do the task manually in the visible browser, then press Enter in the JARVIS window. JARVIS asks for the phrase that should run it next time and saves the navigation, click, fill, and Enter/Tab/Escape steps.

Teach mode does not save passwords, card fields, OTPs, tokens, or secrets. If a learned workflow reaches one of those fields later, JARVIS stops and asks you to handle it.

The recovery chain is:

```text
1. Try exact remembered selector for this site.
2. Run an exact taught workflow when your trigger phrase matches.
3. Try semantic labels: text, aria-label, placeholder, role, title.
4. Re-observe page after action.
5. Use local LLM for one next action only if deterministic paths fail.
6. Stop and ask on login, CAPTCHA, unusual traffic, cookies, payment, checkout, credentials, or permissions.
```

This keeps common commands fast while still letting JARVIS adapt when UI changes.

## Good Command Style

Say the action first, then the target:

```text
open github and search jarvis voice assistant
click first video
find on page pricing
draft a message to Alex saying I am five minutes late
rename this to meeting notes
```

Avoid vague commands when something irreversible is involved. Say `draft` when you do not want it sent.
