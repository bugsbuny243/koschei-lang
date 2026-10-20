# Koschei Lang Mobile v0.1 (experimental)

Native Android Kotlin text editor for Koschei `.ks` files. Open and save via Android Storage Access Framework. Initial example is editable.

**Not yet a compiler or secure execution environment.** No code execution, billing, accounts, internet permission, or backend calls.

GitHub Actions workflow `Android APK (experimental)` builds an unsigned-for-release, debug-signed APK artifact. Open the Actions run from a phone, download the artifact and test locally. Do not publish this debug APK to Google Play.

Build locally with Android SDK 35, JDK 17 and Gradle: `cd android && gradle :app:assembleDebug`. The repository does not yet bundle a Gradle wrapper; CI uses installed Gradle. Verify Android Gradle Plugin/Gradle compatibility in CI.
