import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Read the licensing secret from a gitignored file so it's NEVER committed.
// Copy secret.properties.example -> secret.properties and paste your secret.key
// hex value (the SAME secret your desktop License Console signs with).
val secretProps = Properties().apply {
    val f = rootProject.file("secret.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
val umdSecret: String = (secretProps.getProperty("UMD_SECRET") ?: "").trim()
// Optional: a YouTube Data API v3 key for the Discover tab. Bundled at build time
// from secret.properties (gitignored). Can also be set in-app (Discover settings).
val youtubeApiKey: String = (secretProps.getProperty("YOUTUBE_API_KEY") ?: "").trim()
// Release signing — keystore + passwords live in gitignored secret.properties.
val ksFile = rootProject.file(secretProps.getProperty("KEYSTORE_FILE") ?: "release.keystore")
val ksPassword: String = (secretProps.getProperty("KEYSTORE_PASSWORD") ?: "")
val ksAlias: String = (secretProps.getProperty("KEY_ALIAS") ?: "umd")
val ksKeyPassword: String = (secretProps.getProperty("KEY_PASSWORD") ?: ksPassword)

android {
    namespace = "ke.co.baziqhue.umd"
    compileSdk = 34

    signingConfigs {
        create("release") {
            if (ksFile.exists() && ksPassword.isNotEmpty()) {
                storeFile = ksFile
                storePassword = ksPassword
                keyAlias = ksAlias
                keyPassword = ksKeyPassword
            }
        }
    }

    defaultConfig {
        applicationId = "ke.co.baziqhue.umd"
        minSdk = 26          // 26 lets us ship a vector adaptive icon (no PNGs)
        targetSdk = 34
        versionCode = 35
        versionName = "1.34"

        // Ship native libs only for real Android phones (ARM). Dropping x86/x86_64
        // (emulator-only) roughly halves the bundled engine size — smaller APK +
        // smaller install, with no impact on actual devices.
        ndk { abiFilters += listOf("armeabi-v7a", "arm64-v8a") }

        // Baked into BuildConfig at build time (not in the repo).
        buildConfigField("String", "UMD_SECRET", "\"$umdSecret\"")
        buildConfigField("String", "YOUTUBE_API_KEY", "\"$youtubeApiKey\"")
    }

    buildTypes {
        release {
            // Sign with the release key (kills the "unknown/debug app" install state).
            // Minify stays OFF on purpose: the bundled yt-dlp/ffmpeg/native engine and
            // reflection-based libs are fragile under R8, and the APK weight is native
            // libs (not dex), so shrinking buys little but risks breakage. Stability first.
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    composeOptions { kotlinCompilerExtensionVersion = "1.5.14" }
    // Don't let a lint warning gate the signed release build.
    lint { checkReleaseBuilds = false; abortOnError = false }
    packaging {
        resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" }
        // youtubedl-android ships native libs per ABI
        jniLibs { useLegacyPackaging = true }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.4")
    implementation("androidx.activity:activity-compose:1.9.1")

    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    // The download engine: bundles Python + yt-dlp + ffmpeg for Android.
    // (If a version is not found, let Android Studio suggest the latest.)
    implementation("io.github.junkfood02.youtubedl-android:library:0.17.2")
    implementation("io.github.junkfood02.youtubedl-android:ffmpeg:0.17.2")
    // aria2c (external downloader) removed — unused, and it bundled a large native lib.

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // Encrypted-at-rest storage for the user's AI API key (Android Keystore).
    implementation("androidx.security:security-crypto:1.1.0-alpha06")

    // Reliable HTTP for the AI calls (dead-connection detection / HTTP-2 / retries).
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // Background periodic checks (new uploads from followed artists). Lightweight.
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    // Built-in media player (ExoPlayer + a background MediaSession service + UI).
    implementation("androidx.media3:media3-exoplayer:1.3.1")
    implementation("androidx.media3:media3-session:1.3.1")
    implementation("androidx.media3:media3-ui:1.3.1")

    // Async image loading (channel thumbnails).
    implementation("io.coil-kt:coil-compose:2.6.0")
}
