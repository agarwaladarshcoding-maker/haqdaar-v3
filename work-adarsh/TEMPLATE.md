# <YYYY-MM-DD> — <weekday> · your hands only

**Days to D-day (14 Sep):** <n> · **Milestone in reach:** <v1-skeleton / v1-keypad / …>
**Tool orders for today:** [`work-with-tools/<date>.md`](../work-with-tools/<date>.md)

> Only what a tool cannot do goes in this file: an account, a phone, a card, a decision, a merge.
> If it can be pasted into Antigravity it belongs in `work-with-tools/`, not here.

**Every terminal starts with:**
```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2 && source .venv/bin/activate
```

## ⛔ Blockers — do these first or the rest stalls
- [ ] …

## 🔑 Accounts & admin — do while a tool order is running
- [ ] …

## ✋ Your five minutes per tool order
1. `git checkout -b step-NN` (**R2**)
2. Paste the prompt from the tool file — unedited
3. Run the **Verify** commands
4. Paste the review block into Claude Code with the right `N`
5. On "safe to merge: yes" → `git checkout main && git merge --no-ff step-NN -m "step NN: <name>"`

## 📞 Things only you can do — a phone, a card, a pair of ears
- [ ] …

## ⚖️ Decisions you owe
| By when | The call |
|---|---|
| | |

## 📊 Results to record
| Check | Result |
|---|---|
| | |

## 🌙 End of day — 5 minutes, do not skip
- [ ] `pytest -q`
- [ ] `python3 sync_vault.py --status` → expect 0 dirty
- [ ] Off-script things → one dated line each into `WORK.md` §8
- [ ] Tell Claude Code what merged, so §1 and §6 get updated

**Where I actually got to:**
```
```

**Carrying to tomorrow:**
-
