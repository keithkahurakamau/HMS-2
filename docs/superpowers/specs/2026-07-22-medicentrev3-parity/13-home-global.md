# Module 13 — Home & Global Chrome (`Home` + app shell)

The persistent shell seen on every screen, plus the Home landing.

HMS-2 refs: `App.jsx`, `components/layouts/`, `Home.jsx`, `AdminDashboard.jsx`, `InteractiveDashboard.jsx`, `NotificationBell`, `HospitalPicker`, `ActivePatientBar`, `ThemeToggle` (dark mode), `Seo.jsx`, `queue.py`.

---

## 13.1 Top bar

**Elements:** logo/brand · **"Find a panel"** global search (command-palette style — jump to any screen) · mute/DND icon · **notifications** bell w/ count badge (e.g. 130) · **chat** icon (live chat widget) · **profile** dropdown (avatar + caret) · **connection/wifi** status indicator · **⋮** overflow (Refresh/Back/Forward/Clear/Copy/Paste/Quit).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Notifications bell + count | ✅ Have | `NotificationBell` | — |
| Profile menu / theme | ✅ Have (ahead) | `ThemeToggle` dark mode | — |
| **"Find a panel" global command palette** | 🟡 Partial | quick jump-to-screen search | P3 |
| **Live chat widget** | ❌ Missing | in-app support chat | P3 |
| Connection-status indicator | ❌ Missing | offline/online cue | P3 |

## 13.2 Context header + breadcrumb

**Elements:** **Hospital** name · **Branch** · **Room** (e.g. CONSULTATION ROOM 2) · **[Queue]** button (open room queue) · breadcrumb (home / Module / Screen) · **Guide** link (contextual help).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Hospital/branch context | ✅ Have | `HospitalPicker` + tenant | — |
| **Active Room context + Queue button in header** | 🟡 Partial | HMS-2 has queues; room-scoped header + one-tap Queue? | P2 |
| Breadcrumbs | 🟡 Partial | verify consistent breadcrumbs | P3 |
| **Contextual "Guide" help** per screen | ❌ Missing | inline help/walkthrough | P3 |

## 13.3 Left sidebar

**Elements:** collapsible sidebar (X toggle), 13 icon-labelled modules, expandable sub-menus, active-item highlight.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Module sidebar + nested nav + collapse | ✅ Have | layouts + `ModuleGuard` | — |

## 13.4 Home / landing dashboard

**Elements:** landing dashboard (KPIs/shortcuts). _(MedicentreV3 Home not separately captured.)_

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Home dashboard w/ KPIs | ✅ Have | `Home.jsx` + `InteractiveDashboard` | — |

---

## Global chrome summary

The app shell is a **HMS-2 strength** (sidebar, tenant/branch picker, notifications, **dark mode** — ahead of MedicentreV3). Small polish gaps only:

- 🟡 **Active-room header context + one-tap Queue** — **P2** (pairs with queue/room config, Configuration §9.3)
- 🟡 **"Find a panel" command palette**, ❌ **live chat**, ❌ **contextual Guide**, ❌ connection indicator — P3

No P1 here; the shell is not where MedicentreV3 is ahead.
