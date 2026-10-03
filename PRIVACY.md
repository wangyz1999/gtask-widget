# Privacy Policy

**GTask Widget** · Last updated: October 3, 2026

GTask Widget is an open-source desktop app that shows and edits your Google Tasks. It runs entirely on your computer. This policy explains what it accesses and what it does with that data.

## In short

- **GTask Widget is a pure front end for Google Tasks.** It has no backend, no server and no account system of its own.
- **The developers do not collect, receive, store, use, sell or share any user data.** We never see your tasks or anything else about you.
- **The app accesses only your Google Tasks**, and no other data in your Google account: not your email address, name, profile, contacts, calendar or files.
- **Your tasks travel only between your computer and Google.** The only things saved are on your own computer (your sign-in token and an offline copy of your tasks), encrypted, and deleted when you sign out.

## What the app accesses

When you connect your Google account, the app asks Google for one permission: to view, edit, organize and delete your tasks (OAuth scope `https://www.googleapis.com/auth/tasks`).

The app uses that permission only to:

- show your task lists and tasks in the widget, and
- carry out changes you make in the widget: completing, adding, renaming, scheduling, editing notes, deleting tasks, and creating lists.

The app does not request access to your email address, profile, contacts, calendar, Drive or any other Google data. It never sees your Google password: sign-in happens on Google's own page in your browser.

## What is stored, and where

Everything stays on your computer, in `%APPDATA%\GTaskWidget`:

| File | Contents | Protection |
| --- | --- | --- |
| `token.bin` | Google sign-in token | Encrypted with Windows DPAPI (only your Windows account can read it) |
| `cache.bin` | A copy of your task lists and tasks, so the widget opens instantly and works offline | Encrypted with Windows DPAPI |
| `settings.json` | Appearance, position and filter choices | No personal data |
| `gtask-widget.log` | Diagnostic messages | No task content, no tokens |

## No collection, no sharing

The app talks only to Google's servers (`accounts.google.com`, `oauth2.googleapis.com`, `tasks.googleapis.com`). There is no developer server, no analytics, no crash reporting, no advertising, no telemetry and no third-party SDK. Nothing about you or your tasks is ever sent to the developers or to anyone other than Google, and the developers have no way to access it.

## Google API Services User Data Policy

GTask Widget's use and transfer of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements.

## Your choices

- **Sign out** from the widget's menu. This deletes the token and task cache from your computer and revokes the app's access with Google.
- **Revoke access** at any time from your Google Account: <https://myaccount.google.com/permissions>.
- **Uninstall** the app. The installer's uninstaller also removes `%APPDATA%\GTaskWidget`. For the portable version, delete that folder yourself.

## Children

The app is not directed to children under 13.

## Changes

Any change to this policy will be published in this repository with a new date.

## Contact

Questions or concerns: open an issue at <https://github.com/wangyz1999/gtask-widget/issues>.
