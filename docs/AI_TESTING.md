# Testing the AI features on labbenchos.com

Everything below was tested with fakes only (D245). This is the short list to try with real
accounts after the latest code is deployed. Use a test lab, not a real one.

**If something fails, send back:** which step, the exact error text you see on screen (copy it or
take a screenshot), the time it happened, and the browser. **Never send an API key, an access
token, a code from an address bar, or a screenshot that shows one.** Blur them first.

## Before you start

- [ ] The site is deployed with the latest `main`.
- [ ] In the test lab, Lab details > AI is set to allow both AI apps and the in-app assistant.
- [ ] You can sign in, and you are a member of the test lab.

## 1. Claude: the Connect to Claude button

Needs a claude.ai Pro, Max, Team or Enterprise plan. On Team and Enterprise an owner may have to
allow custom connectors first.

- [ ] In labbenchos, open Settings > AI. Under Connected AI apps, click **Connect to Claude**.
- [ ] claude.ai opens on Add custom connector with the name labbenchos and the address filled in.
      Click Add, then Connect.
- [ ] A labbenchos page opens asking which labs Claude may use, with Read only chosen. Pick the
      test lab, keep Read only, click **Allow**. The page should send you back to Claude.
- [ ] Claude shows labbenchos as connected.
- [ ] In a new Claude chat, turn on the labbenchos connector and ask: "List my labs and projects
      in labbenchos." Claude should call list_labs and list_projects and show your real names.
- [ ] Ask: "What tasks are due this week?" It should list tasks from the test lab only.
- [ ] Ask: "Create a task called Test from Claude in <a project name>." Because you chose Read
      only, Claude should say it needs more access and offer to reconnect. Reconnect, choose
      **Read and write**, and try again. The task should appear in the project, and the lab's
      Audit log should show it as made through Claude.
- [ ] Back in labbenchos Settings > AI, Claude is listed once under Connected AI apps. Click
      Revoke. In Claude, the next request should fail and ask you to reconnect.

## 2. Claude: adding the connector by hand

Same as above, but in claude.ai go to Settings (or Customize) > Connectors > Add custom
connector, name it labbenchos and paste the Connection address shown in labbenchos Settings > AI
(`https://labbenchos.com/mcp`). Leave the advanced OAuth fields empty.

## 3. ChatGPT

Plan requirements are not settled. OpenAI's help pages say full custom connectors (read and write)
are for **Business, Enterprise and Edu**, where a workspace admin must turn on Developer mode
first. Some guides say **Plus and Pro** get read-only connectors. **Free and Go** do not. The menu
has also moved: look for either Settings > Apps & Connectors > Advanced settings > Developer mode,
or Plugins > Add custom MCP server.

- [ ] Note your plan. If it is Business, Enterprise or Edu, ask the admin to allow Developer mode.
- [ ] In ChatGPT, create a new connector (or custom MCP server). Name: labbenchos. Address:
      `https://labbenchos.com/mcp`. Authentication: OAuth. Leave client id and secret empty.
- [ ] A labbenchos page opens. Pick the test lab and Read only, click **Allow**. You should land
      back in ChatGPT with the connector connected.
- [ ] In a chat with the connector on, ask "List my labs in labbenchos" and "What tasks are due
      this week?". It should show real data from the test lab.
- [ ] If your plan allows writes: reconnect with Read and write and ask it to create a task.
      ChatGPT should ask you to confirm before it runs.
- [ ] If ChatGPT shows an error at any step, send the exact text and which step. Most useful:
      whether the labbenchos page opened at all, and whether you got back to ChatGPT after Allow.

## 4. Claude Code with an access token

Needs Claude Code installed on your computer.

- [ ] In labbenchos Settings > AI, under Access tokens, create a token: the test lab, Read only,
      30 days. Copy the command it shows (it starts with `claude mcp add`). The token is shown
      once.
- [ ] Paste the command in a terminal. Run `claude mcp list`: labbenchos should say connected.
- [ ] In Claude Code, ask "Use labbenchos to list my projects." It should list them.
- [ ] Ask it to create a task. It should get "This connection is read-only" back, because the token
      is read only.
- [ ] Revoke the token in Settings. The next request in Claude Code should fail.
- [ ] If Claude Code warns that a tool's output is large, note which question caused it.

## 5. The in-app assistant with an Anthropic key

Needs an Anthropic API key with a little credit (console.anthropic.com). It is billed separately
from any Claude subscription.

- [ ] Settings > AI > Assistant API keys: paste the key under Anthropic and save. It should say
      "key checked and saved" and show only the key's last 4 characters.
- [ ] Open the test lab and click **Assistant**. Choose Claude Opus 5.5. Ask "What projects do we
      have?" The answer streams in, a "List projects" row shows done, and the line under the
      answer shows the model, the tokens and an estimated cost.
- [ ] Ask "Add a task called Test from the assistant to <a project>." A dialog should appear
      naming the project and the task title. Click **Decline**: nothing is created. Ask again and
      click **Approve**: the task appears, and the Audit log shows it as made by you through the
      assistant.
- [ ] Try Sonnet 5.5, Haiku 5.5 and Fable 5.2 in new chats with one short question each. If one
      says your account cannot use the model, send that text.
- [ ] Save a wrong key (change one character). The key check should refuse it with a clear
      message. (If you saved it anyway, a chat should say Anthropic rejected your API key.)

## 6. The in-app assistant with an OpenAI key

The OpenAI part has **never** run against the real API, so this is the most likely to fail.
Needs an OpenAI API key with credit (platform.openai.com).

- [ ] Save the key under OpenAI in Settings > AI > Assistant API keys.
- [ ] Start a new chat, choose OpenAI and the default model. Ask "What projects do we have?"
- [ ] Ask a follow-up in the same chat ("And which tasks are overdue?"). This second turn is the
      one most likely to break, because earlier steps are sent back to OpenAI.
- [ ] Ask it to add a task, then Approve. The task should appear.
- [ ] If anything fails, send the exact message from the chat, which model, and whether it was
      the first or a later message in the chat.

## What should never happen

- Another lab's data in any answer.
- A task or note created without you clicking Approve (in-app) or confirming in Claude/ChatGPT.
- Any error message that shows a key or token.
