# Phone apps

The web app already installs from the browser (README "On your phone"). The store apps are
Capacitor shells in **remote-URL mode**: a native app whose only content is a WebView that loads
the hosted app (`frontend/capacitor.config.ts`, `server.url`). One deploy updates the web, Android
and iOS apps at once, and the cookie-based account works unchanged because the WebView is on the
app's own https origin (a first-party cookie, which `SameSite=Lax` requires). The config refuses
to load without `CAP_SERVER_URL` set to the deployed https address, so a shell can never point at
nothing.

What was done here: `@capacitor/cli`, `core`, `android` and `ios` are installed (dev dependencies),
the config is written and validated with `npx cap config`. `npx cap add android` was **not** run on
the development machine (no Android SDK installed); the GitHub Actions workflow runs it on every
build, and the generated `frontend/android` and `frontend/ios` folders are gitignored.

## Android

A debug APK, built for free by GitHub Actions (`.github/workflows/android.yml`):

1. Repository → Settings → Secrets and variables → Actions → Variables: `CAP_SERVER_URL` =
   `https://<your deployed address>`.
2. Actions → "android" → Run workflow. About five minutes later the run's artifact
   `chess-coach-debug-apk` holds `app-debug.apk`. Copy it to the phone and open it (allow installs
   from unknown sources once). A debug APK is for you and friends; it cannot go to the Play Store.

On a computer with Android Studio (Capacitor 8 needs Node 22, JDK 21 and Android Studio 2025.2 or
newer; `minSdkVersion` 24, target 36):

```bash
cd frontend
CAP_SERVER_URL=https://<address> npx cap add android     # once; creates frontend/android
CAP_SERVER_URL=https://<address> npx cap sync android    # after each config change
CAP_SERVER_URL=https://<address> npx cap open android    # Android Studio: Run, or Build → Generate Signed Bundle
```

Play Store: a one-time $25 developer registration, a signing key (`keytool -genkey ...`, kept out of
git), `./gradlew bundleRelease` for the `.aab`, and since 2024 a personal account must run a closed
test with 12 testers for 14 days before production access. To sign in CI, store the keystore as a
base64 repository secret and decode it in a step before `bundleRelease`; the shipped workflow stops
at the debug APK on purpose.

Deep links and `androidScheme`: the config sets `androidScheme: "https"`, so the WebView's origin is
`https://<address>` exactly as in the browser; nothing on the server changes.

## iOS

No free path to the App Store or to TestFlight: both need an Apple Developer Program membership
($99 a year) and a Mac with Xcode for the build (`npx cap add ios`, `npx cap open ios`, then Xcode's
archive and upload). A personal free Apple ID can sideload a build onto your own iPhone from Xcode
for seven days at a time.

The free iOS path is the web app: Safari → Share → Add to Home Screen. It runs full screen with the
manifest's icon and keeps the account cookie like Safari does.

WKWebView cookie behaviour to know before a store build: with `server.url` the page's origin is the
real https address, so the `Secure`, `HttpOnly`, `SameSite=Lax` cookies are first-party and are
sent with every `fetch`. Community reports describe WKWebView occasionally dropping cookies after a
long time in the background; the cookies here carry `Max-Age` of 400 days, which is the case those
reports say survives. If a signed-in user is logged out after backgrounding, the fix is on the
native side (reload the WebView in `webViewWebContentProcessDidTerminate`), not in the server.

## Icons and splash screens

```bash
cd frontend
npm i -D @capacitor/assets
mkdir -p assets && cp public/icons/icon-512.png assets/icon-only.png   # ideally a 1024x1024 source
npx capacitor-assets generate --android --ios
```

It writes every density into the native projects, so run it after `npx cap add`. A splash screen is
optional; without one Capacitor shows the app's background colour.

## Why not bundle the web build inside the app

A bundled build (`webDir` only, no `server.url`) runs on `capacitor://localhost` on iOS and
`https://localhost` on Android: a different origin from the API, so the cookie becomes third-party,
`SameSite=Lax` blocks it, and every API call would need CORS with credentials and a token scheme.
Remote-URL mode avoids all of that at the cost of needing the network, which the app needs anyway
(the engine and the store live on the server).
