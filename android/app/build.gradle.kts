plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "dev.koschei.langmobile"
    compileSdk = 35
    defaultConfig {
        // Separate experimental install to avoid debug-signature conflict with v0.1.
        applicationId = "dev.koschei.langmobile.preview03"
        minSdk = 26
        targetSdk = 35
        versionCode = 3
        versionName = "0.3.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
