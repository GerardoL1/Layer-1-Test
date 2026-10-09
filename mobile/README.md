# App (iPhone + computer)

One Expo app (SDK 57, React Native, TypeScript) for both the **iPhone** and the **computer**, where it runs in a
browser with Expo web. Narrow screens get the iPhone layout with a bottom tab bar. Wide screens (768 px and up) get
the computer layout with a sidebar. Design: Figma "Field notes" style, Light ("Graph paper") and Dark ("Midnight").

Screens: **Today**, **Trends**, **Profile**, **Setup** (4 steps). Muscles and Train are placeholders for later layers.

## Run on a computer (Windows, Mac or Linux)

Needs Node.js 22.13+, and the server running (`../server/README.md`).

```bash
npm install
npx expo start --web
```

Open `http://localhost:8081`. In **Test build**, keep the server address `http://localhost:8000`, then either load a
demo person (Sam, Alex, Jordan) or type a tester name and click **Use this tester**. On a computer, data comes from
**Import Apple Health export** (Setup step 1, or Profile).

If a code change doesn't show up, restart with `npx expo start --web --clear`.

`http://localhost:8081/components` shows every component with sample data, for comparing against Figma.

## Build for iPhone (needs a Mac)

HealthKit needs a development build, so the app does **not** run in Expo Go.

Needs a Mac with Xcode, an iPhone paired with an Apple Watch worn to bed, and the Mac and iPhone on the same Wi-Fi.

Before the first build:
- In `app.json`, change `ios.bundleIdentifier` (`com.group2.recoverytest`) to something unique to your team.
- On the iPhone: Settings > Privacy & Security > **Developer Mode** on.
- Sign in with your Apple ID in Xcode > Settings > Accounts if asked. Free accounts work, but the app expires after
  7 days.

```bash
npm install
npx expo run:ios --device
```

If the phone blocks the app on first launch, trust it in Settings > General > VPN & Device Management.

### Test checklist

1. Start the server on a computer on the same Wi-Fi (`--host 0.0.0.0`).
2. In the app's Setup, enter `http://<computer-ip>:8000` and a tester name, then **Use this tester**.
3. **Connect Apple Health**, allow the local network prompt, and turn on all four types. The first sync reads the
   last 90 days. The server log should show `[upload]` lines.
4. Profile > Apple Health > **Sync now** should report "Up to date" (only new data is read).
5. The next morning, open Today (or tap **Update now** after waking): last night should appear.
6. Compare a few numbers with the Health app (Heart > Heart Rate Variability, Sleep).

## How the iPhone sync works (`src/health/`)

- **Incremental:** HealthKit gives each data type an *anchor*. Each sync reads only what changed since then. The
  anchor is saved only after the server accepted the upload, so a failed sync just reads the same data again.
- **When:** when the app opens or comes back to the foreground, when HealthKit reports new data (including
  **background delivery**, where iOS wakes the app at most about hourly, often only when unlocked or charging),
  and right before Update now.
- **Time zones:** each reading's UTC offset comes from the watch's `HKTimeZone` tag when present (right after
  travel), otherwise from the phone's offset at that moment.
- **Locked phone:** iOS hides Health data while the phone is locked, so the sync waits.
- **Deleted Health data** is not removed from the server yet.

| File | What it is |
|---|---|
| `health.ios.ts` | HealthKit: permissions, background delivery, anchored sync. Loaded on iPhone only |
| `health.ts` | Does nothing. Loaded on the web, so the computer view never touches HealthKit |
| `convert.ts` | HealthKit sample to upload format, and time zone handling. Tested by `npm test` |
| `HealthSync.tsx` | Decides when to sync and tells screens when new data arrived |

## Code layout

| Folder | What it is |
|---|---|
| `src/app/` | Screens (Expo Router): `(tabs)/` Today, Trends, Profile, Muscles, Train. `setup/` the 4 Setup steps |
| `src/components/` | The Figma components: readiness summary and scale, metric row, charts, list rows, tab bar, sidebar ... |
| `src/theme/` | Colors, fonts and text styles from Figma (`tokens.ts`), Light / Dark switching (`theme.tsx`) |
| `src/api/` | Talks to the server |
| `src/state/` | Server address, tester and appearance, remembered on the device |
| `src/lib/` | Formatting, and the file picker for imports on the web |

## Checks

```bash
npx tsc --noEmit
npx expo lint
npm test
```

Install packages with `npx expo install <package>` so versions match the Expo SDK (see `AGENTS.md`).
