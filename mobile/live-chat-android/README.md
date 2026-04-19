# Live Chat Android Wrapper

This is a lightweight Android wrapper app for the deployed mobile Live Chat route:

- target route: `/mobile/live-chat`
- goal: ship the mobile-first React Live Chat as a real Android app
- backend/auth/APIs/SSE remain the same as the web app

## What it does

- Opens the deployed Live Chat mobile route inside an Android `WebView`
- Keeps browser-like session persistence with WebView storage/cookies
- Supports pull-to-refresh
- Supports in-app back navigation through WebView history
- Enables JavaScript, DOM storage, file upload, microphone/camera permission bridging

## Before building

Set the deployed route in:

- `mobile/live-chat-android/gradle.properties`

Example:

```properties
LIVE_CHAT_URL=https://your-domain/mobile/live-chat
```

## Build outline

1. Open `mobile/live-chat-android` in Android Studio.
2. Let Gradle sync.
3. Confirm `LIVE_CHAT_URL` points to the deployed HTTPS route.
4. Build APK or App Bundle from Android Studio.

## Notes

- The app expects the React app to already serve `/mobile/live-chat`.
- Since auth is web-based, login happens inside the app WebView and remains persisted there.
- If the deployed web app uses a different hostname for APIs, confirm the mobile route still works with the same origin expectations.
